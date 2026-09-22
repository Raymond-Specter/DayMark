import json
import re
from pathlib import Path

from sqlalchemy import select

from ..models import AgentActionLog
from ..services.common import local_now, settings
from ..services.llm.base import LLMError, Message
from .schemas import AgentOutcome

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
PROMPT = (PROMPT_DIR / "agent_system_prompt.txt").read_text(encoding="utf-8")
MANUAL = (PROMPT_DIR / "agent_manual.md").read_text(encoding="utf-8")


class AgentService:
    def __init__(self, llm, registry, executor, session_factory, max_steps=8):
        self.llm, self.registry, self.executor = llm, registry, executor
        self.session_factory, self.max_steps = session_factory, max_steps

    def system_prompt(self, db):
        current = local_now(db)
        prompt = PROMPT.format(current_datetime=current.strftime("%Y-%m-%d %H:%M:%S"),
                               timezone=settings(db).timezone)
        return f"{prompt}\n\n{MANUAL}"

    def system_prompt_for_conversation(self, db, conversation_id):
        prompt = self.system_prompt(db)
        logs = list(db.scalars(select(AgentActionLog).where(
            AgentActionLog.conversation_id == conversation_id,
            AgentActionLog.status == "success",
        ).order_by(AgentActionLog.created_at.desc()).limit(8)))
        if logs:
            references = []
            for log in logs:
                state = log.after_state or {}
                references.append({"tool": log.tool_name, "id": state.get("id"),
                                   "title": state.get("title") or state.get("name"),
                                   "date": state.get("date"), "start_time": state.get("start_time")})
            prompt += "\n\n当前会话最近成功操作的实体引用（只能用于定位，真实当前状态仍应查询 Tool）：\n" + json.dumps(references, ensure_ascii=False)
        return prompt

    async def run(self, conversation_id, messages, options, emit, mode="local", request_id=None):
        affected, confirmation, metrics = [], None, {}
        failed_calls = {}
        working = list(messages)
        user_text = next((message.content for message in reversed(working) if message.role == "user"), "")
        requires_tool = self._requires_tool(user_text)
        # Completed prose from earlier turns can teach a small local model to
        # imitate an answer instead of invoking a tool. Action context is kept
        # in the system prompt as verified entity references, so tool-bound
        # turns only need the system prompt and the current user request.
        if requires_tool:
            working = [working[0], working[-1]]
        used_tools = False
        successful_write = False
        tool_count = 0
        route = self.llm.create_session(mode, options) if hasattr(self.llm, "create_session") else None
        if route:
            await emit({"event": "provider_status", "provider": route.name, "model": route.options.model})
        available_tools = self._tool_schemas(user_text)
        for _ in range(self.max_steps):
            while True:
                content, reasoning, calls = "", "", []
                stream = (route.stream_chat(working, available_tools) if route
                          else self.llm.stream_chat(working, options, available_tools))
                try:
                    async for chunk in stream:
                        metrics.update(chunk.metrics)
                        calls.extend(chunk.tool_calls)
                        reasoning += chunk.reasoning_content
                        if chunk.content:
                            content += chunk.content
                            await emit({"event": "delta", "content": chunk.content})
                    break
                except LLMError as error:
                    if route and route.try_fallback(error, successful_write):
                        if content:
                            await emit({"event": "reset"})
                        await emit({"event": "provider_status", "provider": route.name,
                                    "model": route.options.model, "fallback": True,
                                    "message": "DeepSeek 暂时不可用，已切换到本地 Qwen。"})
                        continue
                    if successful_write:
                        if content:
                            await emit({"event": "reset"})
                        metrics.update({"provider_error": error.code, "write_completed": True})
                        return AgentOutcome(content="操作已经完成，但 AI 最终回复生成失败。请刷新任务或日历查看结果。",
                                            metrics=metrics, affected_entities=self._unique(affected),
                                            confirmation=confirmation)
                    raise
                finally:
                    await stream.aclose()
            if not calls:
                if route:
                    metrics.update({"provider": route.name, "model": route.options.model,
                                    "fallback": route.fell_back, "tool_count": tool_count})
                if requires_tool and not used_tools:
                    if self._is_clarification(content):
                        return AgentOutcome(content=content, metrics=metrics)
                    if content:
                        await emit({"event": "reset"})
                    working[0] = Message("system", working[0].content +
                        "\n当前请求涉及真实规划数据或操作，上一响应没有调用工具，不能作为最终回答。必须立即调用合适的已注册工具；如果信息不足，明确询问用户，绝不能声称已执行。")
                    continue
                if not content.strip():
                    raise LLMError("empty_answer", "模型未返回最终回答，请重试。", 502)
                return AgentOutcome(content=content, metrics=metrics,
                                    affected_entities=self._unique(affected), confirmation=confirmation)
            if content:
                await emit({"event": "reset"})
            used_tools = True
            working.append(Message("assistant", content, tool_calls=calls,
                                   reasoning_content=reasoning or None))
            for call in calls:
                function = call.get("function", {})
                name, arguments = function.get("name", ""), function.get("arguments", {})
                arguments = self._normalize_tool_arguments(name, arguments, user_text)
                definition = self.registry.definitions.get(name)
                status = definition.status_text if definition else "正在处理操作…"
                await emit({"event": "tool_status", "tool": name, "message": status})
                tool_count += 1
                result = self.executor.execute(
                    conversation_id, name, arguments, request_id=request_id,
                    provider=route.name if route else metrics.get("provider", "local"),
                    model=route.options.model if route else options.model,
                )
                if definition and definition.permission.value != "read" and result.success:
                    successful_write = True
                affected.extend(result.affected_entities)
                confirmation = result.confirmation or confirmation
                await emit({"event": "tool_result", "tool": name, "success": result.success,
                            "message": result.message, "affected_entities": result.affected_entities,
                            "confirmation": result.confirmation})
                call_id = call.get("id") or f"{name}-{len(working)}"
                working.append(Message("tool", result.model_dump_json(), tool_call_id=call_id))
                if not result.success and not result.confirmation:
                    signature = json.dumps({"tool": name, "arguments": arguments,
                                            "error_code": result.error_code}, ensure_ascii=False, sort_keys=True)
                    failed_calls[signature] = failed_calls.get(signature, 0) + 1
                    if failed_calls[signature] >= 2:
                        return AgentOutcome(
                            content=f"无法执行这个操作：{result.message}", metrics=metrics,
                            affected_entities=self._unique(affected), confirmation=confirmation)
        if route:
            metrics.update({"provider": route.name, "model": route.options.model,
                            "fallback": route.fell_back, "tool_count": tool_count})
        raise LLMError("tool_loop_limit", "工具调用次数过多，已停止且保留已经成功完成的操作。", 409)

    @staticmethod
    def _requires_tool(text):
        markers = ("安排", "创建", "新建", "添加", "新增", "导入", "加入", "加到", "加上去", "记到", "放到",
                   "改到", "改期", "重新安排", "完成", "取消", "撤销", "删除", "暂停",
                   "保存", "记录", "更新", "修改", "归档", "恢复", "重新打开", "保留逾期", "标记已读",
                   "有哪些任务", "什么任务", "查看任务", "查询任务", "空闲时间", "日历", "截止", "重复任务",
                   "每天", "每日", "每周", "工作日", "隔天", "定期", "每隔",
                   "目标", "项目", "里程碑", "学习档案", "学习记录", "知识库", "每日复盘", "数据统计",
                   "会议", "日程", "复盘", "统计", "完成率", "整体进度", "偏好设置", "模型设置", "时区", "通知", "导出")
        return any(marker in text for marker in markers)

    def _tool_schemas(self, text):
        names = {"get_tasks", "get_calendar", "get_free_slots"}
        create_words = ("安排", "创建", "新建", "添加", "新增", "加入", "加到", "加上去", "记到", "放到", "保存", "记录")
        update_words = ("修改", "更新", "改成", "改为", "编辑", "归档", "恢复")
        delete_words = ("删除", "移除")
        recurring = any(marker in text for marker in
                        ("重复", "Routine", "routine", "每天", "每日", "每周", "工作日", "周一到周五", "隔天", "定期", "每隔"))
        learning_entry = ("学习档案" in text or "学习记录" in text or
                          ("记录" in text and any(marker in text for marker in ("学了", "学习了", "实际学习", "进度", "反思"))))
        if "撤销" in text:
            names = {"undo_last_action"}
        elif (("课表" in text or "课程表" in text or ("[附件：" in text and ".pdf]" in text.lower()))
              and any(marker in text for marker in ("安排", "创建", "添加", "新增", "导入", "加入", "加到", "加上去", "记到", "放到"))):
            names = {"import_timetable"}
        elif "知识库" in text or "知识文档" in text:
            if any(word in text for word in delete_words): names = {"get_documents", "delete_document"}
            elif any(word in text for word in update_words): names = {"get_documents", "update_document"}
            elif (any(marker in text.lower() for marker in ("附件", "刚上传", "上传的", "文件", ".pdf", ".docx", ".md", ".txt"))
                  and any(word in text for word in create_words)):
                names = {"get_projects", "save_attachment_to_knowledge"}
            else: names = {"get_documents"}
        elif learning_entry:
            if any(word in text for word in delete_words): names = {"get_learning_entries", "delete_learning_entry"}
            elif any(word in text for word in update_words): names = {"get_learning_entries", "update_learning_entry"}
            elif any(word in text for word in create_words): names = {"get_projects", "get_tasks", "create_learning_entry"}
            else: names = {"get_learning_entries"}
        elif "复盘" in text:
            names = {"get_projects", "get_daily_review", "save_daily_review"} if any(
                word in text for word in create_words + update_words + ("写", "填写")) else {"get_daily_review"}
        elif any(marker in text for marker in ("数据统计", "统计", "完成率", "计划时间", "实际时间", "项目时间分布")):
            names = {"get_statistics"}
        elif any(marker in text for marker in ("整体进度", "目标进度", "项目进度", "当前阶段")):
            names = {"get_progress"}
        elif "偏好设置" in text or "默认开始时间" in text or "时区" in text:
            names = {"get_settings", "update_settings"} if any(word in text for word in update_words) else {"get_settings"}
        elif "模型设置" in text or "AI 模式" in text or "Thinking" in text or "上下文长度" in text:
            names = {"get_ai_settings", "update_ai_settings"} if any(word in text for word in update_words) else {"get_ai_settings"}
        elif "导出" in text or "备份数据" in text:
            names = {"prepare_data_export"}
        elif "通知" in text or "提醒消息" in text:
            names = {"get_notifications", "mark_notification_read"} if "已读" in text else {"get_notifications"}
        elif ("目标" in text and "项目" in text and not recurring
              and any(word in text for word in create_words)):
            names = {"create_goal", "get_goals", "create_project"}
            if "里程碑" in text or "阶段节点" in text:
                names.update({"get_projects", "create_milestone"})
        elif ("里程碑" in text or "阶段节点" in text) and not recurring:
            if any(word in text for word in delete_words): names = {"get_milestones", "delete_milestone"}
            elif any(word in text for word in update_words): names = {"get_milestones", "update_milestone"}
            elif any(word in text for word in create_words): names = {"get_projects", "create_milestone"}
            else: names = {"get_milestones"}
        elif ("项目" in text and not recurring
              and not any(marker in text for marker in ("项目时间", "项目进度", "项目会议", "日程", "日历事项"))):
            if any(word in text for word in delete_words): names = {"get_projects", "delete_project"}
            elif any(word in text for word in update_words): names = {"get_goals", "get_projects", "update_project"}
            elif any(word in text for word in create_words): names = {"get_goals", "create_project"}
            else: names = {"get_projects"}
        elif "目标" in text and not recurring:
            if any(word in text for word in delete_words): names = {"get_goals", "delete_goal"}
            elif any(word in text for word in update_words): names = {"get_goals", "update_goal"}
            elif any(word in text for word in create_words): names = {"create_goal"}
            else: names = {"get_goals"}
        elif recurring:
            if any(word in text for word in delete_words): names = {"get_routines", "delete_routine"}
            elif "暂停" in text: names = {"get_routines", "pause_routine"}
            elif any(word in text for word in update_words): names = {"get_routines", "update_routine"}
            elif any(word in text for word in create_words) or "从" in text: names = {"get_projects", "get_routines", "create_routine"}
            else: names = {"get_routines"}
        elif any(marker in text for marker in ("独立日历事项", "日历事项", "会议", "日程")) and "任务" not in text:
            if any(word in text for word in delete_words): names = {"get_calendar", "delete_event"}
            elif any(word in text for word in update_words): names = {"get_calendar", "update_event"}
            elif (any(word in text for word in create_words)
                  or any(marker in text for marker in ("有个", "有一场", "要开", "参加"))):
                names = {"get_calendar", "create_event"}
            else: names = {"get_calendar"}
        elif "任务" in text and any(marker in text for marker in ("重新打开", "恢复")):
            names = {"get_tasks", "reopen_task"}
        elif "保留逾期" in text:
            names = {"get_tasks", "keep_task_overdue"}
        elif "任务" in text and any(word in text for word in update_words):
            names = {"get_tasks", "update_task"}
        elif "未完成" in text:
            names = {"get_tasks"}
        elif "完成" in text:
            names = {"get_today_tasks", "get_tasks", "complete_task"}
        elif "删除" in text:
            names = {"get_tasks", "delete_task"}
        elif "取消" in text:
            names = {"get_tasks", "cancel_task"}
        elif "重新安排" in text and ("有事" in text or "冲突" in text):
            names = {"get_calendar", "replan_day"}
        elif any(marker in text for marker in ("改到", "改期", "重新安排")):
            names = {"get_tasks", "reschedule_task", "update_task"}
        elif any(marker in text for marker in (*create_words, "找个时间")):
            names = {"get_free_slots", "create_task", "schedule_task"}
        elif "今天" in text and "任务" in text:
            names = {"get_today_tasks"}
        if ("截止" in text and names == {"get_tasks", "get_calendar", "get_free_slots"}
                and any(marker in text for marker in ("查看", "哪些", "临近", "未来", "查询"))):
            names = {"get_upcoming_deadlines"}
        return [self.registry.definitions[name].provider_schema() for name in names if name in self.registry.definitions]

    @staticmethod
    def _is_clarification(content):
        text = content.strip()
        return bool(text) and ("？" in text or "?" in text or any(
            marker in text for marker in ("请提供", "请告诉", "请确认", "需要知道", "缺少", "无法确定")))

    @staticmethod
    def _normalize_tool_arguments(name, arguments, user_text):
        if name != "create_task" or not isinstance(arguments, dict):
            return arguments
        normalized = dict(arguments)
        start_time = normalized.get("start_time") or normalized.get("time")
        explicit_duration = re.search(r"\d+(?:\.\d+)?\s*(?:分钟|小时|min(?:ute)?s?|hours?)", user_text, re.IGNORECASE)
        if start_time and not normalized.get("end_time") and not explicit_duration:
            if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start_time):
                hour, minute = map(int, start_time.split(":"))
                duration = normalized.get("duration_minutes", 30)
                remaining = 23 * 60 + 59 - (hour * 60 + minute)
                if isinstance(duration, int) and 0 < remaining < duration:
                    normalized["duration_minutes"] = remaining
                    normalized["end_time"] = "23:59"
        return normalized

    @staticmethod
    def _unique(rows):
        seen, result = set(), []
        for row in rows:
            key = (row.get("type"), row.get("id"))
            if key not in seen:
                seen.add(key)
                result.append(row)
        return result

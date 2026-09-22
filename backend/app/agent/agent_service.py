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
        markers = ("安排", "创建", "添加", "新增", "导入", "加入", "加到", "加上去", "记到", "放到",
                   "改到", "改期", "重新安排", "完成", "取消", "撤销", "删除", "暂停",
                   "有哪些任务", "什么任务", "查看任务", "查询任务", "空闲时间", "日历", "截止", "重复任务")
        return any(marker in text for marker in markers)

    def _tool_schemas(self, text):
        names = {"get_tasks", "get_calendar", "get_free_slots"}
        if "撤销" in text:
            names = {"undo_last_action"}
        elif "完成" in text:
            names = {"get_today_tasks", "complete_task"}
        elif "删除" in text:
            names = {"get_tasks", "delete_task"}
        elif "取消" in text:
            names = {"get_tasks", "cancel_task"}
        elif "重新安排" in text and ("有事" in text or "冲突" in text):
            names = {"get_calendar", "replan_day"}
        elif any(marker in text for marker in ("改到", "改期", "重新安排")):
            names = {"get_tasks", "reschedule_task", "update_task"}
        elif (("课表" in text or "课程表" in text or ("[附件：" in text and ".pdf]" in text.lower()))
              and any(marker in text for marker in ("安排", "创建", "添加", "新增", "导入", "加入", "加到", "加上去", "记到", "放到"))):
            names = {"import_timetable"}
        elif "重复" in text or "Routine" in text or "routine" in text:
            names = {"get_routines", "create_routine", "update_routine", "pause_routine"}
        elif any(marker in text for marker in ("安排", "创建", "添加", "新增", "加入", "加到", "加上去", "记到", "放到", "找个时间")):
            names = {"get_free_slots", "create_task", "schedule_task"}
        elif "今天" in text and "任务" in text:
            names = {"get_today_tasks"}
        if "截止" in text:
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

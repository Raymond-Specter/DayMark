import json
import hashlib
from datetime import date, timedelta

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text

from ..models import AgentActionLog, PendingAgentAction, now_iso
from .permissions import ToolPermission
from .schemas import ToolResult
from .tools import PlanningTools
from .clarification import pending_question, question_dict
from .daily_planner import DailyPlanner


class ToolExecutor:
    def __init__(self, registry, session_factory):
        self.registry, self.session_factory = registry, session_factory

    def execute(self, conversation_id: str, name: str, arguments, allow_destructive=False,
                request_id=None, provider=None, model=None, expected_plan=None):
        try:
            definition = self.registry.require(name)
        except ValueError:
            return ToolResult(success=False, error_code="UNKNOWN_TOOL", message="模型请求了未注册的工具，未执行任何操作。")
        try:
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            arguments = self._normalize_arguments(name, arguments or {})
            checked = definition.arguments.model_validate(arguments or {})
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError):
            return ToolResult(success=False, error_code="INVALID_ARGUMENTS",
                              message="工具参数格式不正确，请使用要求的绝对日期、时间和字段。")
        with self.session_factory() as db:
            # Hold the SQLite write lock while revalidating and applying a preview.
            if name == "plan_daily_tasks" and allow_destructive:
                db.execute(text("BEGIN IMMEDIATE"))
            question = pending_question(db, conversation_id)
            if question and definition.permission != ToolPermission.READ:
                return ToolResult(success=False, error_code="INFORMATION_REQUIRED",
                                  message="请先回答待确认的问题，未执行任何写入。", clarification=question_dict(question))
            fingerprint = None
            if definition.permission != ToolPermission.READ and request_id:
                canonical = json.dumps(checked.model_dump(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                fingerprint = hashlib.sha256(f"{conversation_id}:{request_id}:{name}:{canonical}".encode()).hexdigest()
                previous = db.scalar(select(AgentActionLog).where(
                    AgentActionLog.fingerprint == fingerprint, AgentActionLog.status == "success"))
                if previous:
                    return ToolResult(success=True, message="该操作已在本次请求中成功执行，已跳过重复调用。",
                                      data=previous.after_state, affected_entities=previous.affected_entities or [])
            tools = PlanningTools(db, conversation_id)
            if name == "plan_daily_tasks":
                try:
                    if allow_destructive:
                        preview = DailyPlanner(db).preview(checked)
                        if expected_plan is None or preview != expected_plan:
                            return ToolResult(success=False, error_code="PLAN_CHANGED",
                                              message="日历或时间条件已变化，本次没有创建任务。请重新生成并确认规划。")
                    else:
                        handled = tools.plan_daily_tasks(checked)
                        if handled.result.clarification:
                            db.commit()
                            return handled.result
                        preview = handled.result.data
                        pending = PendingAgentAction(
                            conversation_id=conversation_id, tool_name=name,
                            tool_arguments={**checked.model_dump(), "_preview": preview},
                            description=f"新增“{checked.title}”，共 {len(preview['days'])} 天、{preview['task_count']} 个任务；保留原有安排。",
                            affected_count=preview["task_count"], request_id=request_id,
                            provider=provider, model=model,
                        )
                        db.add(pending)
                        db.flush()
                        confirmation = self._confirmation(pending)
                        db.commit()
                        return ToolResult(success=False, error_code="CONFIRMATION_REQUIRED",
                                          message="逐日规划已生成，请查看预览并确认；尚未创建任务。",
                                          data=preview, confirmation=confirmation)
                except (HTTPException, ValueError) as error:
                    db.rollback()
                    return ToolResult(success=False, error_code="INVALID_PLAN", message=self._safe_error(error))
            affected_count = (len(tools.replan_candidates(checked)) if name == "replan_day"
                              else len(checked.courses) if name == "import_timetable" else 1)
            needs_confirmation = (definition.permission == ToolPermission.DESTRUCTIVE
                                  or name == "import_timetable"
                                  or (name == "replan_day" and affected_count > 3))
            if needs_confirmation and not allow_destructive:
                pending = PendingAgentAction(
                    conversation_id=conversation_id, tool_name=name,
                    tool_arguments=checked.model_dump(), description=self._description(name, checked),
                    affected_count=affected_count,
                    request_id=request_id, provider=provider, model=model,
                )
                db.add(pending)
                db.commit()
                return ToolResult(success=False, error_code="CONFIRMATION_REQUIRED",
                                  message="此操作需要确认。", confirmation={
                                      "action_id": pending.id, "tool": name,
                                      "arguments": pending.tool_arguments,
                                      "description": pending.description,
                                      "affected_count": pending.affected_count,
                                  })
            try:
                handled = (tools.apply_daily_plan(checked, expected_plan) if name == "plan_daily_tasks"
                           else getattr(tools, definition.handler)(checked))
                if definition.permission != ToolPermission.READ:
                    db.add(AgentActionLog(
                        conversation_id=conversation_id, tool_name=name,
                        tool_arguments=checked.model_dump(), permission_level=definition.permission.value,
                        status="success" if handled.result.success else "rejected",
                        before_state=handled.before, after_state=handled.after,
                        affected_entities=handled.result.affected_entities,
                        error_message=None if handled.result.success else handled.result.message,
                        request_id=request_id, provider=provider, model=model,
                        fingerprint=fingerprint if handled.result.success else None,
                    ))
                db.commit()
                return handled.result
            except Exception as error:
                db.rollback()
                message = self._safe_error(error)
                if definition.permission != ToolPermission.READ:
                    db.add(AgentActionLog(
                        conversation_id=conversation_id, tool_name=name,
                        tool_arguments=checked.model_dump(), permission_level=definition.permission.value,
                        status="error", before_state=None, after_state=None,
                        affected_entities=[], error_message=message,
                        request_id=request_id, provider=provider, model=model,
                    ))
                    db.commit()
                return ToolResult(success=False, error_code="TOOL_FAILED", message=message)

    def confirm(self, conversation_id: str, action_id: str, approve: bool,
                request_id=None, provider=None, model=None):
        with self.session_factory() as db:
            pending = db.get(PendingAgentAction, action_id)
            if not pending or pending.conversation_id != conversation_id or pending.status != "pending":
                raise HTTPException(404, "待确认操作不存在或已经处理")
            if pending.tool_name == "ask_user":
                raise HTTPException(422, "请通过问题卡片回答，不能替用户确认答案。")
            pending.status = "approved" if approve else "cancelled"
            pending.resolved_at = now_iso()
            db.commit()
            name, arguments = pending.tool_name, pending.tool_arguments
            expected_plan = arguments.get("_preview") if name == "plan_daily_tasks" else None
            if name == "plan_daily_tasks":
                arguments = {key: value for key, value in arguments.items() if key != "_preview"}
            request_id = request_id or pending.request_id
            provider = provider or pending.provider
            model = model or pending.model
        if not approve:
            return ToolResult(success=False, error_code="CANCELLED", message="已取消该操作。")
        return self.execute(conversation_id, name, arguments, allow_destructive=True,
                            request_id=request_id or action_id, provider=provider, model=model,
                            expected_plan=expected_plan)

    @staticmethod
    def _confirmation(pending):
        return {"action_id": pending.id, "tool": pending.tool_name,
                "arguments": {key: value for key, value in pending.tool_arguments.items() if key != "_preview"},
                "description": pending.description, "affected_count": pending.affected_count,
                "preview": pending.tool_arguments.get("_preview")}

    @staticmethod
    def _safe_error(error):
        if isinstance(error, HTTPException) and isinstance(error.detail, str):
            return error.detail
        if isinstance(error, ValueError):
            return str(error)[:300]
        return "工具执行失败，数据未修改。"

    @staticmethod
    def _normalize_arguments(name, arguments):
        if not isinstance(arguments, dict):
            return arguments
        normalized = dict(arguments)
        if name == "create_task":
            # Qwen occasionally follows the human word "time" even though the
            # advertised schema says start_time. This alias is unambiguous.
            if "time" in normalized and "start_time" not in normalized:
                normalized["start_time"] = normalized.pop("time")
            # In Chinese usage, "今晚24点" means 00:00 of the next calendar day.
            if normalized.get("start_time") == "24:00" and normalized.get("date"):
                normalized["date"] = (date.fromisoformat(normalized["date"]) + timedelta(days=1)).isoformat()
                normalized["start_time"] = "00:00"
        return normalized

    @staticmethod
    def _description(name, arguments):
        if name == "delete_task":
            return f"删除任务 {arguments.task_id}，任务及历史数据将从正常界面隐藏。"
        if name == "replan_day":
            return f"重新安排 {arguments.date} {arguments.blocked_start}–{arguments.blocked_end} 内的大批冲突任务。"
        if name == "import_timetable":
            weekday_labels = {name: "周" + label for name, label in zip(
                ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"), "一二三四五六日")}
            lines = [f"{course.name}（{','.join(weekday_labels[day] for day in course.weekdays)} {course.start_time}–{course.end_time}）"
                     for course in arguments.courses]
            return (f"导入 {arguments.start_date} 至 {arguments.end_date} 的 {len(lines)} 门课程："
                    + "；".join(lines))
        return f"执行 {name}。"

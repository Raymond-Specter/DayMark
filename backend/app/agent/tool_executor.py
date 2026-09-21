import json
from datetime import date, timedelta

from fastapi import HTTPException
from pydantic import ValidationError

from ..models import AgentActionLog, PendingAgentAction, now_iso
from .permissions import ToolPermission
from .schemas import ToolResult
from .tools import PlanningTools


class ToolExecutor:
    def __init__(self, registry, session_factory):
        self.registry, self.session_factory = registry, session_factory

    def execute(self, conversation_id: str, name: str, arguments, allow_destructive=False):
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
            tools = PlanningTools(db, conversation_id)
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
                handled = getattr(tools, definition.handler)(checked)
                if definition.permission != ToolPermission.READ:
                    db.add(AgentActionLog(
                        conversation_id=conversation_id, tool_name=name,
                        tool_arguments=checked.model_dump(), permission_level=definition.permission.value,
                        status="success" if handled.result.success else "rejected",
                        before_state=handled.before, after_state=handled.after,
                        affected_entities=handled.result.affected_entities,
                        error_message=None if handled.result.success else handled.result.message,
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
                    ))
                    db.commit()
                return ToolResult(success=False, error_code="TOOL_FAILED", message=message)

    def confirm(self, conversation_id: str, action_id: str, approve: bool):
        with self.session_factory() as db:
            pending = db.get(PendingAgentAction, action_id)
            if not pending or pending.conversation_id != conversation_id or pending.status != "pending":
                raise HTTPException(404, "待确认操作不存在或已经处理")
            pending.status = "approved" if approve else "cancelled"
            pending.resolved_at = now_iso()
            db.commit()
            name, arguments = pending.tool_name, pending.tool_arguments
        if not approve:
            return ToolResult(success=False, error_code="CANCELLED", message="已取消该操作。")
        return self.execute(conversation_id, name, arguments, allow_destructive=True)

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

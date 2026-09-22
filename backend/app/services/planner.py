from fastapi import HTTPException
from sqlalchemy import select, update

from ..models import Milestone, Project, Routine, Task, TaskHistory, now_iso
from ..schemas import TaskIn
from .calendar import CalendarService
from .common import effective_status, raw, require, task_dependency
from .reminder import ReminderService


class PlannerService:
    """User-directed changes only. Scheduling and reminder delivery are separate."""

    def __init__(self, db):
        self.db = db

    def validate_links(self, values):
        if values.get("project_id"):
            require(self.db, Project, values["project_id"])
        if values.get("milestone_id"):
            milestone = require(self.db, Milestone, values["milestone_id"])
            if milestone.project_id != values.get("project_id"):
                raise HTTPException(422, "里程碑必须属于选中的项目")

    def validate_dependency(self, task_id, parent_id):
        seen = {task_id} if task_id else set()
        while parent_id:
            if parent_id in seen:
                raise HTTPException(422, "任务依赖不能指向自己或形成循环")
            seen.add(parent_id)
            parent_id = require(self.db, Task, parent_id).depends_on_task_id

    def after_task(self, task, action, before=None):
        self.db.flush()
        self.db.add(TaskHistory(task_id=task.id, action=action, before=before or {}, after=raw(task)))
        CalendarService(self.db).sync_task(task)
        ReminderService(self.db).schedule(task)
        self.db.flush()
        return task

    def create_task(self, data):
        values = data.model_dump(exclude={"version"})
        self.validate_links(values)
        self.validate_dependency(None, values.get("depends_on_task_id"))
        task = Task(**values, source="manual", status="pending")
        self.db.add(task)
        return self.after_task(task, "created")

    def mutate(self, task, values, expected_version, action, exception=True):
        if expected_version != task.version:
            raise HTTPException(409, "此任务已被其他页面修改，请刷新后重试")
        before = raw(task)
        values.update(version=task.version + 1, updated_at=now_iso())
        if exception and task.routine_id:
            values["is_exception"] = True
        changed = self.db.execute(update(Task).where(Task.id == task.id, Task.version == expected_version).values(**values))
        if changed.rowcount != 1:
            raise HTTPException(409, "此任务已更新，请刷新后重试")
        self.db.refresh(task)
        return self.after_task(task, action, before)

    def update_task(self, task, data):
        if data.version is None:
            raise HTTPException(422, "更新任务需要 version")
        values = data.model_dump(exclude={"version"})
        self.validate_links(values)
        self.validate_dependency(task.id, values.get("depends_on_task_id"))
        # A user choosing/clearing a generated dependency makes this occurrence explicit.
        if values["depends_on_task_id"] != task.depends_on_task_id or not values["depends_on_task_id"]:
            values["depends_on_routine_id"] = None
        if any(values[key] != getattr(task, key) for key in ("date", "start_time", "end_time")) and task.status not in {"completed", "cancelled"}:
            values["status"] = "rescheduled"
        return self.mutate(task, values, data.version, "edited")

    def action(self, task, data):
        values = {}
        if data.action == "complete":
            if task.status == "cancelled":
                raise HTTPException(409, "请先重新打开已取消的任务")
            blocked, reason, _ = task_dependency(self.db, task)
            if blocked:
                raise HTTPException(409, reason)
            values = {"status": "completed", "completed_at": task.completed_at or now_iso()}
        elif data.action == "reopen":
            dependents = list(self.db.scalars(select(Task).where(Task.depends_on_task_id == task.id, Task.status == "completed", Task.deleted_at.is_(None))))
            if dependents:
                raise HTTPException(409, "请先重新打开已完成的后续依赖任务")
            values = {"status": "pending", "completed_at": None}
        elif data.action == "cancel":
            if task.status == "completed":
                raise HTTPException(409, "请先重新打开已完成的任务")
            values = {"status": "cancelled", "completed_at": None}
        elif data.action == "keep_overdue":
            if effective_status(self.db, task) != "overdue":
                raise HTTPException(409, "只有逾期任务可以保留为逾期")
            values = {"status": "overdue"}
        elif data.action == "reschedule":
            if task.status in {"completed", "cancelled"}:
                raise HTTPException(409, "请先重新打开任务再改期")
            if not data.date:
                raise HTTPException(422, "改期需要新日期")
            fields = {key: getattr(task, key) for key in TaskIn.model_fields if key != "version"}
            fields.update(date=data.date, start_time=data.start_time if "start_time" in data.model_fields_set else task.start_time,
                          end_time=data.end_time if "end_time" in data.model_fields_set else task.end_time)
            checked = TaskIn(**fields)
            values = {"date": checked.date, "start_time": checked.start_time, "end_time": checked.end_time,
                      "estimated_duration": checked.estimated_duration, "status": "rescheduled"}
        return self.mutate(task, values, data.version, data.action)

    def delete(self, task, version):
        dependent = self.db.scalar(select(Task).where(Task.depends_on_task_id == task.id, Task.deleted_at.is_(None)))
        if dependent:
            raise HTTPException(409, "仍有任务依赖此任务，请先修改依赖")
        return self.mutate(task, {"deleted_at": now_iso()}, version, "deleted")

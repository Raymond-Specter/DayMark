from dataclasses import dataclass
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select, update

from ..models import AgentActionLog, CalendarEvent, Routine, Task, now_iso
from ..schemas import RoutineIn, TaskAction, TaskIn
from ..services.calendar import CalendarService
from ..services.common import live_tasks, raw, require, sorted_tasks, task_dict, today
from ..services.planner import PlannerService
from ..services.scheduler import SchedulerService
from .planner_service import AgentPlannerService, clock, minutes
from .schemas import ToolResult
from .workspace_tools import WorkspaceTools


@dataclass
class Handled:
    result: ToolResult
    before: dict | None = None
    after: dict | None = None


class PlanningTools(WorkspaceTools):
    def __init__(self, db, conversation_id: str):
        self.db, self.conversation_id = db, conversation_id
        self.planner = AgentPlannerService(db)

    def ok(self, message, data=None, affected=None, before=None, after=None):
        return Handled(ToolResult(success=True, message=message, data=data,
                                  affected_entities=affected or []), before, after)

    def get_today_tasks(self, _):
        rows = [task_dict(self.db, task) for task in live_tasks(self.db) if task.date == today(self.db).isoformat()]
        return self.ok(f"今天共有 {len(rows)} 个任务。", rows)

    def get_tasks(self, args):
        rows = sorted_tasks(self.db, live_tasks(self.db))
        if args.date:
            rows = [row for row in rows if row["date"] == args.date]
        if args.start_date:
            rows = [row for row in rows if row["date"] and row["date"] >= args.start_date]
        if args.end_date:
            rows = [row for row in rows if row["date"] and row["date"] <= args.end_date]
        if args.project_id:
            rows = [row for row in rows if row["project_id"] == args.project_id]
        if args.status:
            rows = [row for row in rows if row["status"] == args.status]
        return self.ok(f"找到 {len(rows)} 个任务。", rows)

    def get_calendar(self, args):
        start = args.date or args.start_date or today(self.db).isoformat()
        end = args.date or args.end_date or start
        exclusive = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
        SchedulerService(self.db).materialize(date.fromisoformat(start), date.fromisoformat(end))
        events = CalendarService(self.db).list_events(start, exclusive)
        return self.ok(f"日历中有 {len(events)} 个事项。", events)

    def get_free_slots(self, args):
        slots = self.planner.free_slots(args.date, args.earliest_time, args.latest_time, args.min_duration_minutes)
        return self.ok(f"找到 {len(slots)} 个满足条件的空闲时段。", slots)

    def get_routines(self, _):
        rows = [raw(row) for row in self.db.scalars(select(Routine).where(Routine.deleted_at.is_(None)).order_by(Routine.created_at))]
        return self.ok(f"共有 {len(rows)} 个重复任务。", rows)

    def get_upcoming_deadlines(self, args):
        start = today(self.db)
        end = (start + timedelta(days=args.days)).isoformat()
        rows = [task_dict(self.db, task) for task in live_tasks(self.db)
                if task.deadline and task.status not in {"completed", "cancelled"}
                and start.isoformat() <= task.deadline[:10] <= end]
        rows.sort(key=lambda item: item["deadline"])
        return self.ok(f"未来 {args.days} 天有 {len(rows)} 个截止事项。", rows)

    def create_task(self, args):
        task, conflicts = self.planner.create(args.title, args.date, args.start_time, args.end_time,
                                              args.duration_minutes, args.project_id, args.priority, args.description,
                                              args.milestone_id, args.deadline, args.reminder,
                                              args.depends_on_task_id, args.track_learning)
        if conflicts:
            return Handled(ToolResult(success=False, error_code="TIME_CONFLICT",
                                      message="指定时间与现有日历事项冲突。", data={"conflicts": conflicts}))
        entity = {"type": "task", "id": task.id}
        timing = task.date
        if task.start_time:
            timing += f" {task.start_time}–{task.end_time}"
        return self.ok(
            f"已创建任务“{task.title}”：{timing}，预计 {task.estimated_duration} 分钟。",
            task_dict(self.db, task), [entity], None, raw(task))

    def update_task(self, args):
        task = require(self.db, Task, args.task_id)
        before = raw(task)
        fields = {key: getattr(task, key) for key in TaskIn.model_fields if key != "version"}
        supplied = args.model_dump(exclude_unset=True, exclude={"task_id"})
        if "duration_minutes" in supplied:
            supplied["estimated_duration"] = supplied.pop("duration_minutes")
        fields.update(supplied)
        checked = TaskIn(**fields, version=task.version)
        if checked.start_time:
            finish = checked.end_time or clock(minutes(checked.start_time) + checked.estimated_duration)
            conflicts = self.planner.conflicts(checked.date, checked.start_time, finish, task.id)
            if conflicts:
                return Handled(ToolResult(success=False, error_code="TIME_CONFLICT",
                                          message="修改后的时间与现有日历事项冲突。", data={"conflicts": conflicts}))
        task = PlannerService(self.db).update_task(task, checked)
        return self.ok(f"已更新任务“{task.title}”。", task_dict(self.db, task),
                       [{"type": "task", "id": task.id}], before, raw(task))

    def reschedule_task(self, args):
        task = require(self.db, Task, args.task_id)
        before = raw(task)
        task, conflicts = self.planner.reschedule(task, args.new_date, args.new_start_time, args.new_end_time)
        if conflicts:
            return Handled(ToolResult(success=False, error_code="TIME_CONFLICT",
                                      message="新时间与现有日历事项冲突。", data={"conflicts": conflicts}))
        return self.ok(f"已把“{task.title}”改到 {task.date} {task.start_time or '全天'}。", task_dict(self.db, task),
                       [{"type": "task", "id": task.id}], before, raw(task))

    def complete_task(self, args):
        task = require(self.db, Task, args.task_id)
        before = raw(task)
        task = PlannerService(self.db).action(task, TaskAction(action="complete", version=task.version))
        return self.ok(f"已完成任务“{task.title}”。", task_dict(self.db, task),
                       [{"type": "task", "id": task.id}], before, raw(task))

    def reopen_task(self, args):
        task = require(self.db, Task, args.task_id)
        before = raw(task)
        task = PlannerService(self.db).action(task, TaskAction(action="reopen", version=task.version))
        return self.ok(f"已重新打开任务“{task.title}”。", task_dict(self.db, task),
                       [{"type": "task", "id": task.id}], before, raw(task))

    def cancel_task(self, args):
        task = require(self.db, Task, args.task_id)
        before = raw(task)
        task = PlannerService(self.db).action(task, TaskAction(action="cancel", version=task.version))
        return self.ok(f"已取消任务“{task.title}”。", task_dict(self.db, task),
                       [{"type": "task", "id": task.id}], before, raw(task))

    def keep_task_overdue(self, args):
        task = require(self.db, Task, args.task_id)
        before = raw(task)
        task = PlannerService(self.db).action(task, TaskAction(action="keep_overdue", version=task.version))
        return self.ok(f"已保留逾期任务“{task.title}”。", task_dict(self.db, task),
                       [{"type": "task", "id": task.id}], before, raw(task))

    def create_routine(self, args):
        values = args.model_dump()
        checked = RoutineIn(**values)
        PlannerService(self.db).validate_links(checked.model_dump())
        SchedulerService(self.db).validate_dependency(None, checked.depends_on_routine_id)
        row = Routine(**checked.model_dump(exclude={"version"}))
        self.db.add(row)
        self.db.flush()
        SchedulerService(self.db).materialize()
        return self.ok(f"已创建重复任务“{row.name}”。", raw(row),
                       [{"type": "routine", "id": row.id}], None, raw(row))

    def import_timetable(self, args):
        weekday_numbers = {name: index for index, name in enumerate(
            ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"))}
        rows = []
        for course in args.courses:
            start = minutes(course.start_time)
            end = minutes(course.end_time)
            description = " · ".join(part for part in (course.location, course.notes) if part)
            checked = RoutineIn(
                name=course.name, description=description, frequency="weekdays", interval=1,
                interval_unit="weeks", weekdays=[weekday_numbers[day] for day in course.weekdays], start_date=args.start_date,
                end_date=args.end_date, preferred_time=course.start_time,
                estimated_duration=end - start, priority=2, active=True,
            )
            row = Routine(**checked.model_dump(exclude={"version"}))
            self.db.add(row)
            rows.append(row)
        self.db.flush()
        SchedulerService(self.db).materialize()
        data = [raw(row) for row in rows]
        affected = [{"type": "routine", "id": row.id} for row in rows]
        return self.ok(
            f"已导入 {len(rows)} 门课程，生效范围为 {args.start_date} 至 {args.end_date}。",
            data, affected, None, {"routines": data})

    def update_routine(self, args):
        row = require(self.db, Routine, args.routine_id)
        before = raw(row)
        was_active = row.active
        values = {key: getattr(row, key) for key in RoutineIn.model_fields if key != "version"}
        values.update(args.model_dump(exclude_unset=True, exclude={"routine_id"}))
        checked = RoutineIn(**values, version=row.version)
        PlannerService(self.db).validate_links(checked.model_dump())
        SchedulerService(self.db).validate_dependency(row.id, checked.depends_on_routine_id)
        SchedulerService(self.db).materialize(end=today(self.db))
        changes = checked.model_dump(exclude={"version"})
        if not was_active and checked.active:
            changes["materialized_through"] = max(
                row.materialized_through or "0001-01-01", (today(self.db) - timedelta(days=1)).isoformat())
        changed = self.db.execute(update(Routine).where(Routine.id == row.id, Routine.version == row.version)
                                  .values(**changes, version=row.version + 1, updated_at=now_iso()))
        if changed.rowcount != 1:
            raise HTTPException(409, "重复任务已更新，请重试")
        self.db.refresh(row)
        SchedulerService(self.db).refresh_future(row)
        return self.ok(f"已更新重复任务“{row.name}”。", raw(row),
                       [{"type": "routine", "id": row.id}], before, raw(row))

    def pause_routine(self, args):
        row = require(self.db, Routine, args.routine_id)
        before = raw(row)
        row.active, row.version, row.updated_at = False, row.version + 1, now_iso()
        SchedulerService(self.db).refresh_future(row)
        self.db.flush()
        return self.ok(f"已暂停重复任务“{row.name}”。", raw(row),
                       [{"type": "routine", "id": row.id}], before, raw(row))

    def delete_routine(self, args):
        row = require(self.db, Routine, args.routine_id)
        if self.db.scalar(select(Routine).where(Routine.depends_on_routine_id == row.id,
                                                Routine.deleted_at.is_(None))):
            raise HTTPException(409, "其他重复任务仍依赖此规则，请先修改依赖")
        before = raw(row)
        row.active, row.deleted_at, row.version = False, now_iso(), row.version + 1
        SchedulerService(self.db).refresh_future(row)
        self.db.flush()
        return self.ok(f"已删除重复任务“{row.name}”。", {"deleted": True},
                       [{"type": "routine", "id": row.id}], before, raw(row))

    def schedule_task(self, args):
        task, conflicts = self.planner.schedule(args.title, args.date, args.duration_minutes,
                                                args.preferred_period, args.earliest_time,
                                                args.latest_time, args.project_id)
        if not task:
            return Handled(ToolResult(success=False, error_code="NO_FREE_SLOT",
                                      message="指定时段内没有足够长的空闲时间。", data={"conflicts": conflicts}))
        return self.ok(f"已把“{task.title}”安排在 {task.date} {task.start_time}–{task.end_time}。",
                       task_dict(self.db, task), [{"type": "task", "id": task.id}], None, raw(task))

    def replan_day(self, args):
        if not args.blocked_start or not args.blocked_end:
            return Handled(ToolResult(success=False, error_code="BLOCK_REQUIRED", message="请提供明确的占用开始和结束时间。"))
        blocked = (minutes(args.blocked_start), minutes(args.blocked_end))
        if blocked[1] <= blocked[0]:
            return Handled(ToolResult(success=False, error_code="INVALID_TIME", message="占用结束时间必须晚于开始时间。"))
        tasks = self.replan_candidates(args)
        moved, unresolved, before_rows = [], [], []
        for task in tasks:
            before = raw(task)
            slots = self.planner.free_slots(args.date, minimum=max(15, task.estimated_duration), extra_blocks=[blocked])
            candidate = next((slot for slot in slots if slot["start_time"] >= args.blocked_end or slot["end_time"] <= args.blocked_start), None)
            if not candidate:
                unresolved.append({"id": task.id, "title": task.title})
                continue
            start_time = candidate["start_time"]
            moved_task, conflicts = self.planner.reschedule(task, args.date, start_time,
                                                            clock(minutes(start_time) + max(15, task.estimated_duration)))
            if not moved_task or conflicts:
                unresolved.append({"id": task.id, "title": task.title})
                continue
            before_rows.append(before)
            moved.append(task_dict(self.db, moved_task))
        affected = [{"type": "task", "id": row["id"]} for row in moved]
        return self.ok(f"已重新安排 {len(moved)} 个冲突任务，{len(unresolved)} 个未解决。",
                       {"moved_tasks": moved, "unresolved_tasks": unresolved}, affected,
                       {"tasks": before_rows}, {"tasks": [raw(require(self.db, Task, row["id"])) for row in moved]})

    def replan_candidates(self, args):
        if not args.blocked_start or not args.blocked_end:
            return []
        blocked = (minutes(args.blocked_start), minutes(args.blocked_end))
        return [task for task in live_tasks(self.db)
                if task.date == args.date and task.start_time
                and task.status not in {"completed", "cancelled"}
                and minutes(task.start_time) < blocked[1]
                and minutes(task.end_time or clock(minutes(task.start_time) + task.estimated_duration)) > blocked[0]]

    def delete_task(self, args):
        task = require(self.db, Task, args.task_id)
        before = raw(task)
        PlannerService(self.db).delete(task, task.version)
        return self.ok(f"已删除任务“{task.title}”。", None, [{"type": "task", "id": task.id}], before, raw(task))

    def undo_last_action(self, _):
        reversible = {"create_task", "schedule_task", "update_task", "reschedule_task", "complete_task", "replan_day"}
        log = self.db.scalar(select(AgentActionLog).where(
            AgentActionLog.conversation_id == self.conversation_id,
            AgentActionLog.status == "success", AgentActionLog.undone_at.is_(None),
            AgentActionLog.tool_name.in_(reversible),
        ).order_by(AgentActionLog.created_at.desc()))
        if not log:
            return Handled(ToolResult(success=False, error_code="NOTHING_TO_UNDO", message="没有可以撤销的最近操作。"))
        state = log.after_state or {}
        if log.tool_name == "replan_day":
            restored = []
            for before in (log.before_state or {}).get("tasks", []):
                task = require(self.db, Task, before.get("id"))
                allowed = {column.name for column in Task.__table__.columns} - {"id", "created_at", "updated_at", "version"}
                values = {key: value for key, value in before.items() if key in allowed}
                PlannerService(self.db).mutate(task, values, task.version, "agent_undo", exception=False)
                restored.append(task)
            log.undone_at, log.status = now_iso(), "undone"
            self.db.flush()
            return self.ok(f"已撤销最近的 replan_day 操作，恢复 {len(restored)} 个任务。",
                           {"restored_tasks": [task_dict(self.db, row) for row in restored]},
                           [{"type": "task", "id": row.id} for row in restored], state,
                           {"tasks": [raw(row) for row in restored]})
        task = require(self.db, Task, state.get("id"))
        if log.tool_name in {"create_task", "schedule_task"}:
            PlannerService(self.db).delete(task, task.version)
        else:
            before = log.before_state or {}
            allowed = {column.name for column in Task.__table__.columns} - {"id", "created_at", "updated_at", "version"}
            values = {key: value for key, value in before.items() if key in allowed}
            PlannerService(self.db).mutate(task, values, task.version, "agent_undo", exception=False)
        log.undone_at, log.status = now_iso(), "undone"
        self.db.flush()
        return self.ok(f"已撤销最近的 {log.tool_name} 操作。", task_dict(self.db, task),
                       [{"type": "task", "id": task.id}], state, raw(task))

from datetime import date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from ..models import Routine, Task, now_iso, uid
from .common import require, today
from .planner import PlannerService


def matches(routine, day):
    start = date.fromisoformat(routine.start_date)
    if day < start or (routine.end_date and day > date.fromisoformat(routine.end_date)):
        return False
    delta = (day - start).days
    if routine.frequency == "daily":
        return True
    if routine.frequency == "every_n_days":
        return delta % routine.interval == 0
    if routine.frequency == "weekly":
        return delta % (7 * routine.interval) == 0
    if routine.frequency == "weekdays":
        monday = start - timedelta(days=start.weekday())
        return day.weekday() in routine.weekdays and ((day - monday).days // 7) % routine.interval == 0
    step = routine.interval * (7 if routine.interval_unit == "weeks" else 1)
    return delta % step == 0


def sequence(routine, day):
    start = date.fromisoformat(routine.start_date)
    delta = (day - start).days
    if routine.frequency == "daily":
        return delta + 1
    if routine.frequency in {"every_n_days", "weekly", "custom"}:
        factor = 7 if routine.frequency == "weekly" or (routine.frequency == "custom" and routine.interval_unit == "weeks") else 1
        return delta // (routine.interval * factor) + 1
    # Count weekday matches without scanning every date since inception.
    monday = start - timedelta(days=start.weekday())
    week = (day - monday).days // 7
    full_cycles = week // routine.interval
    count = full_cycles * len(routine.weekdays)
    count += sum(1 for weekday in routine.weekdays if weekday <= day.weekday())
    count -= sum(1 for weekday in routine.weekdays if weekday < start.weekday())
    return count


class SchedulerService:
    def __init__(self, db):
        self.db = db
        self.planner = PlannerService(db)
        self.created = 0

    def validate_dependency(self, routine_id, parent_id):
        seen = {routine_id} if routine_id else set()
        while parent_id:
            if parent_id in seen:
                raise HTTPException(422, "重复任务依赖不能指向自己或形成循环")
            seen.add(parent_id)
            parent_id = require(self.db, Routine, parent_id).depends_on_routine_id

    def values(self, routine, day):
        number = sequence(routine, day)
        start_time, end_time = routine.preferred_time, None
        if start_time:
            end_time = (datetime.fromisoformat(f"{day}T{start_time}") + timedelta(minutes=routine.estimated_duration)).strftime("%H:%M")
        parent_id = None
        if routine.depends_on_routine_id:
            parent_routine = self.db.get(Routine, routine.depends_on_routine_id)
            parent = self.ensure(parent_routine, day - timedelta(days=routine.offset_days)) if parent_routine else None
            parent_id = parent.id if parent else None
        return {
            "title": routine.name.replace("{n}", str(number)).replace("{date}", day.isoformat()),
            "description": routine.description, "project_id": routine.project_id, "milestone_id": routine.milestone_id,
            "date": day.isoformat(), "start_time": start_time, "end_time": end_time,
            "estimated_duration": routine.estimated_duration, "priority": routine.priority, "reminder": routine.reminder,
            "routine_id": routine.id, "occurrence_date": day.isoformat(), "sequence_number": number,
            "depends_on_routine_id": routine.depends_on_routine_id, "depends_on_task_id": parent_id,
            "offset_days": routine.offset_days,
        }

    def ensure(self, routine, day):
        if routine is None:
            return None
        existing = self.db.scalar(select(Task).where(Task.routine_id == routine.id, Task.occurrence_date == day.isoformat()))
        if existing:
            return existing
        if routine.materialized_through and day <= today(self.db) and day.isoformat() <= routine.materialized_through:
            return None
        if not routine.active or routine.deleted_at or not matches(routine, day):
            return None
        values = self.values(routine, day)
        self.planner.validate_dependency(None, values.get("depends_on_task_id"))
        task_id = uid()
        result = self.db.execute(insert(Task).values(id=task_id, source="routine", status="pending", **values).on_conflict_do_nothing(index_elements=["routine_id", "occurrence_date"]))
        if result.rowcount:
            task = self.db.get(Task, task_id)
            self.planner.after_task(task, "generated")
            self.created += 1
            return task
        return self.db.scalar(select(Task).where(Task.routine_id == routine.id, Task.occurrence_date == day.isoformat()))

    def materialize(self, start=None, end=None):
        current = today(self.db)
        end = end or current + timedelta(days=30)
        if start and start > end:
            raise HTTPException(422, "开始日期不能晚于结束日期")
        if start and (end - start).days > 366:
            raise HTTPException(422, "单次生成范围不能超过 367 天")
        if not start and end > current + timedelta(days=366):
            raise HTTPException(422, "远期生成请同时指定开始和结束日期")
        routines = list(self.db.scalars(select(Routine).where(Routine.active.is_(True), Routine.deleted_at.is_(None))))
        # A durable high-water mark catches up after downtime without reinterpreting
        # historical dates using an edited rule. Calendar ranges extend coverage.
        for routine in routines:
            first = date.fromisoformat(routine.start_date)
            if routine.materialized_through:
                first = max(first, date.fromisoformat(routine.materialized_through) + timedelta(days=1))
            contiguous_start = first
            if start:
                first = max(first, start)
            last = min(end, date.fromisoformat(routine.end_date)) if routine.end_date else end
            day = first
            while day <= last:
                if matches(routine, day):
                    self.ensure(routine, day)
                day += timedelta(days=1)
            if last >= first and first == contiguous_start:
                routine.materialized_through = last.isoformat()
        # Link children whose predecessor was absent when they were created.
        unresolved = self.db.scalars(select(Task).where(Task.depends_on_routine_id.is_not(None), Task.depends_on_task_id.is_(None), Task.is_exception.is_(False), Task.deleted_at.is_(None)))
        for task in unresolved:
            source_day = date.fromisoformat(task.occurrence_date) - timedelta(days=task.offset_days)
            parent = self.db.scalar(select(Task).where(Task.routine_id == task.depends_on_routine_id, Task.occurrence_date == source_day.isoformat()))
            if parent:
                self.planner.validate_dependency(task.id, parent.id)
                self.planner.mutate(task, {"depends_on_task_id": parent.id}, task.version, "dependency_linked", exception=False)
        self.db.flush()
        return self.created

    def refresh_future(self, routine):
        future = list(self.db.scalars(select(Task).where(
            Task.routine_id == routine.id, Task.occurrence_date > today(self.db).isoformat(),
            Task.is_exception.is_(False), Task.deleted_at.is_(None), Task.status != "completed",
        )))
        for task in future:
            day = date.fromisoformat(task.occurrence_date)
            values = self.values(routine, day) if routine.active and not routine.deleted_at and matches(routine, day) else {}
            self.planner.validate_dependency(task.id, values.get("depends_on_task_id"))
            values["status"] = "pending" if values else "cancelled"
            self.planner.mutate(task, values, task.version, "routine_updated", exception=False)
        # New weekdays in an already materialized future range need new occurrences.
        # Earlier history is never regenerated from the replacement rule.
        day = max(today(self.db) + timedelta(days=1), date.fromisoformat(routine.start_date))
        last = date.fromisoformat(routine.materialized_through) if routine.materialized_through else today(self.db)
        while routine.active and not routine.deleted_at and day <= last:
            if matches(routine, day):
                self.ensure(routine, day)
            day += timedelta(days=1)
        self.materialize()

from datetime import datetime, timedelta

from sqlalchemy import select

from ..models import CalendarEvent, Task
from ..schemas import TaskAction, TaskIn
from ..services.common import require, settings
from ..services.planner import PlannerService


def minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def clock(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


class AgentPlannerService:
    """Deterministic conflict detection and first-fit scheduling."""

    def __init__(self, db):
        self.db = db

    def occupied(self, day: str, exclude_task_id: str | None = None):
        start, end = f"{day}T00:00:00", f"{day}T23:59:59"
        rows = self.db.scalars(select(CalendarEvent).where(CalendarEvent.start < end, CalendarEvent.end > start))
        result = []
        for event in rows:
            if event.task_id == exclude_task_id:
                continue
            task = self.db.get(Task, event.task_id) if event.task_id else None
            if task and (task.deleted_at or task.status == "cancelled"):
                continue
            # Untimed tasks stay in the task list. Standalone all-day events
            # reserve the day and therefore remove timed free slots.
            if event.all_day:
                if event.task_id:
                    continue
                result.append({"start": "00:00", "end": "23:59", "title": event.title,
                               "task_id": None, "event_id": event.id})
                continue
            result.append({"start": event.start[11:16], "end": event.end[11:16], "title": event.title,
                           "task_id": event.task_id, "event_id": event.id})
        return sorted(result, key=lambda item: item["start"])

    def conflicts(self, day, start_time, end_time, exclude_task_id=None):
        if not start_time or not end_time:
            return []
        begin, finish = minutes(start_time), minutes(end_time)
        return [item for item in self.occupied(day, exclude_task_id)
                if minutes(item["start"]) < finish and minutes(item["end"]) > begin]

    def free_slots(self, day, earliest_time=None, latest_time=None, minimum=30, extra_blocks=None):
        start = minutes(earliest_time or settings(self.db).day_start)
        end = minutes(latest_time or "23:00")
        busy = [(minutes(item["start"]), minutes(item["end"])) for item in self.occupied(day)]
        busy.extend(extra_blocks or [])
        merged = []
        for begin, finish in sorted(busy):
            begin, finish = max(start, begin), min(end, finish)
            if finish <= begin:
                continue
            if merged and begin <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], finish))
            else:
                merged.append((begin, finish))
        slots, cursor = [], start
        for begin, finish in merged:
            if begin - cursor >= minimum:
                slots.append({"start_time": clock(cursor), "end_time": clock(begin), "duration_minutes": begin - cursor})
            cursor = max(cursor, finish)
        if end - cursor >= minimum:
            slots.append({"start_time": clock(cursor), "end_time": clock(end), "duration_minutes": end - cursor})
        return slots

    def create(self, title, day, start_time, end_time, duration, project_id=None, priority=2, description="",
               milestone_id=None, deadline=None, reminder=None, depends_on_task_id=None, track_learning=False):
        if start_time and not end_time:
            finish = minutes(start_time) + duration
            if finish >= 1440:
                raise ValueError("任务不能跨过午夜")
            end_time = clock(finish)
        conflicts = self.conflicts(day, start_time, end_time)
        if conflicts:
            return None, conflicts
        task = PlannerService(self.db).create_task(TaskIn(
            title=title, date=day, start_time=start_time, end_time=end_time,
            estimated_duration=duration, project_id=project_id, priority=priority, description=description,
            milestone_id=milestone_id, deadline=deadline, reminder=reminder,
            depends_on_task_id=depends_on_task_id, track_learning=track_learning,
        ))
        return task, []

    def reschedule(self, task, day, start_time, end_time):
        if start_time and not end_time:
            finish = minutes(start_time) + max(15, task.estimated_duration)
            if finish >= 1440:
                raise ValueError("任务不能跨过午夜")
            end_time = clock(finish)
        conflicts = self.conflicts(day, start_time, end_time, task.id)
        if conflicts:
            return None, conflicts
        result = PlannerService(self.db).action(task, TaskAction(
            action="reschedule", date=day, start_time=start_time, end_time=end_time, version=task.version,
        ))
        return result, []

    def schedule(self, title, day, duration, preferred_period=None, earliest_time=None, latest_time=None, project_id=None):
        periods = {"morning": ("09:00", "12:00"), "afternoon": ("12:00", "18:00"), "evening": ("18:00", "23:00")}
        if preferred_period:
            earliest_time, latest_time = periods[preferred_period]
        slots = self.free_slots(day, earliest_time, latest_time, duration)
        if not slots:
            return None, []
        begin = slots[0]["start_time"]
        return self.create(title, day, begin, clock(minutes(begin) + duration), duration, project_id)

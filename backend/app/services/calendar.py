from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import select

from ..models import CalendarEvent, Task
from .common import task_color, task_dict


class CalendarProvider(Protocol):
    """Reserved boundary for external synchronization; no provider is configured."""

    def upsert(self, event: dict) -> str: ...
    def delete(self, external_id: str) -> None: ...


class CalendarService:
    def __init__(self, db):
        self.db = db

    def sync_task(self, task):
        event = self.db.scalar(select(CalendarEvent).where(CalendarEvent.task_id == task.id))
        if not task.date or task.deleted_at or task.status == "cancelled":
            if event:
                self.db.delete(event)
            return
        all_day = not task.start_time
        start = task.date if all_day else f"{task.date}T{task.start_time}:00"
        if all_day:
            end = (datetime.fromisoformat(task.date) + timedelta(days=1)).date().isoformat()
        elif task.end_time:
            end = f"{task.date}T{task.end_time}:00"
        else:
            end = (datetime.fromisoformat(start) + timedelta(minutes=max(15, task.estimated_duration))).isoformat()
        if event is None:
            event = CalendarEvent(task_id=task.id)
            self.db.add(event)
        event.title, event.start, event.end = task.title, start, end
        event.all_day, event.description, event.color = all_day, task.description, task_color(self.db, task)

    def list_events(self, start, end):
        events = self.db.scalars(select(CalendarEvent).where(CalendarEvent.start < end, CalendarEvent.end > start))
        result = []
        for event in events:
            task = self.db.get(Task, event.task_id) if event.task_id else None
            color = task_color(self.db, task) if task else event.color
            result.append({
                "id": event.id, "title": event.title, "start": event.start, "end": event.end,
                "allDay": event.all_day, "backgroundColor": color, "borderColor": color,
                "classNames": ["task-completed"] if task and task.status == "completed" else [],
                "extendedProps": {"task_id": event.task_id, "task": task_dict(self.db, task) if task else None,
                                  "description": event.description, "color": color},
            })
        return result

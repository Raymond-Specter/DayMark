from datetime import datetime, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import select, update

from ..models import Notification, ReminderJob, Task
from .common import settings, utc_now


class ReminderProvider(Protocol):
    """Future provider adapters receive an already persisted reminder job."""

    def deliver(self, job: ReminderJob, task: Task) -> str: ...


class ReminderService:
    def __init__(self, db):
        self.db = db

    def schedule(self, task):
        self.db.execute(update(ReminderJob).where(
            ReminderJob.task_id == task.id, ReminderJob.status == "pending"
        ).values(status="cancelled"))
        if task.reminder is None or task.status in {"completed", "cancelled"} or task.deleted_at:
            return
        pref = settings(self.db)
        if task.date:
            anchor = datetime.fromisoformat(f"{task.date}T{task.start_time or pref.day_start}").replace(tzinfo=ZoneInfo(pref.timezone))
        elif task.deadline:
            anchor = datetime.fromisoformat(task.deadline)
        else:
            return
        due = (anchor.astimezone(timezone.utc) - timedelta(minutes=task.reminder)).isoformat()
        already_delivered = self.db.scalar(select(ReminderJob.id).where(
            ReminderJob.task_id == task.id, ReminderJob.due_at == due, ReminderJob.status == "delivered"
        ))
        if already_delivered:
            return
        existing = self.db.scalar(select(ReminderJob).where(ReminderJob.task_id == task.id, ReminderJob.task_version == task.version))
        if existing:
            # A dispatched version never becomes a new reminder on reload.
            if existing.status != "delivered":
                existing.status, existing.due_at = "pending", due
            return
        self.db.add(ReminderJob(task_id=task.id, task_version=task.version, due_at=due))

    def dispatch(self):
        delivered = 0
        jobs = list(self.db.scalars(select(ReminderJob).where(ReminderJob.status == "pending", ReminderJob.due_at <= utc_now().isoformat())))
        for job in jobs:
            task = self.db.get(Task, job.task_id)
            if not task or task.deleted_at or task.status in {"completed", "cancelled"} or task.version != job.task_version:
                job.status = "cancelled"
                continue
            # Conditional claim + unique notification key make retries safe.
            claimed = self.db.execute(update(ReminderJob).where(ReminderJob.id == job.id, ReminderJob.status == "pending").values(status="delivered"))
            if claimed.rowcount:
                self.db.add(Notification(job_id=job.id, task_id=task.id, title=task.title, due_at=job.due_at))
                delivered += 1
        self.db.flush()
        return delivered

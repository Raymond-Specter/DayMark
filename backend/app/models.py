from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def uid():
    return str(uuid4())


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[str] = mapped_column(String, default=now_iso)
    updated_at: Mapped[str] = mapped_column(String, default=now_iso, onupdate=now_iso)


class Goal(Record, Base):
    __tablename__ = "goals"
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    start_date: Mapped[str | None] = mapped_column(String(10))
    target_date: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String, default="active")
    priority: Mapped[int] = mapped_column(Integer, default=2)
    color: Mapped[str] = mapped_column(String(7), default="#4f6ef7")


class Project(Record, Base):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(String(200))
    goal_id: Mapped[str | None] = mapped_column(ForeignKey("goals.id", ondelete="RESTRICT"), index=True)
    start_date: Mapped[str | None] = mapped_column(String(10))
    end_date: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String, default="active")
    description: Mapped[str] = mapped_column(Text, default="")


class Milestone(Record, Base):
    __tablename__ = "milestones"
    name: Mapped[str] = mapped_column(String(200))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), index=True)
    start_date: Mapped[str | None] = mapped_column(String(10))
    deadline: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String, default="active")
    description: Mapped[str] = mapped_column(Text, default="")


class Routine(Record, Base):
    __tablename__ = "routines"
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), index=True)
    milestone_id: Mapped[str | None] = mapped_column(ForeignKey("milestones.id", ondelete="RESTRICT"))
    frequency: Mapped[str] = mapped_column(String)
    interval: Mapped[int] = mapped_column(Integer, default=1)
    interval_unit: Mapped[str] = mapped_column(String, default="days")
    weekdays: Mapped[list] = mapped_column(JSON, default=list)
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str | None] = mapped_column(String(10))
    preferred_time: Mapped[str | None] = mapped_column(String(5))
    estimated_duration: Mapped[int] = mapped_column(Integer, default=30)
    priority: Mapped[int] = mapped_column(Integer, default=2)
    reminder: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    depends_on_routine_id: Mapped[str | None] = mapped_column(ForeignKey("routines.id", ondelete="RESTRICT"))
    offset_days: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    deleted_at: Mapped[str | None] = mapped_column(String)
    materialized_through: Mapped[str | None] = mapped_column(String(10))
    __table_args__ = (CheckConstraint("interval >= 1"), CheckConstraint("offset_days >= 0"))


class Task(Record, Base):
    __tablename__ = "tasks"
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), index=True)
    milestone_id: Mapped[str | None] = mapped_column(ForeignKey("milestones.id", ondelete="RESTRICT"))
    date: Mapped[str | None] = mapped_column(String(10), index=True)
    start_time: Mapped[str | None] = mapped_column(String(5))
    end_time: Mapped[str | None] = mapped_column(String(5))
    deadline: Mapped[str | None] = mapped_column(String, index=True)
    estimated_duration: Mapped[int] = mapped_column(Integer, default=30)
    priority: Mapped[int] = mapped_column(Integer, default=2)
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    completed_at: Mapped[str | None] = mapped_column(String, index=True)
    source: Mapped[str] = mapped_column(String, default="manual")
    routine_id: Mapped[str | None] = mapped_column(ForeignKey("routines.id", ondelete="RESTRICT"))
    occurrence_date: Mapped[str | None] = mapped_column(String(10))
    sequence_number: Mapped[int | None] = mapped_column(Integer)
    depends_on_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"))
    depends_on_routine_id: Mapped[str | None] = mapped_column(ForeignKey("routines.id", ondelete="RESTRICT"))
    offset_days: Mapped[int] = mapped_column(Integer, default=0)
    reminder: Mapped[int | None] = mapped_column(Integer)
    is_exception: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[str | None] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("routine_id", "occurrence_date", name="uq_routine_occurrence"),
        CheckConstraint("priority BETWEEN 1 AND 3"),
        CheckConstraint("estimated_duration >= 0"),
        CheckConstraint("status IN ('pending','completed','overdue','rescheduled','cancelled')"),
    )


class TaskHistory(Record, Base):
    __tablename__ = "task_history"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    action: Mapped[str] = mapped_column(String)
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)


class CalendarEvent(Record, Base):
    __tablename__ = "calendar_events"
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    start: Mapped[str] = mapped_column(String)
    end: Mapped[str] = mapped_column(String)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    color: Mapped[str] = mapped_column(String(7), default="#4f6ef7")
    description: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String, default="local")
    external_id: Mapped[str | None] = mapped_column(String)
    __table_args__ = (Index("ix_event_range", "start", "end"),)


class ReminderJob(Record, Base):
    __tablename__ = "reminder_jobs"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    due_at: Mapped[str] = mapped_column(String, index=True)
    task_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="pending")
    channel: Mapped[str] = mapped_column(String, default="in_app")
    __table_args__ = (UniqueConstraint("task_id", "task_version", name="uq_reminder_version"),)


class Notification(Record, Base):
    __tablename__ = "notifications"
    job_id: Mapped[str] = mapped_column(ForeignKey("reminder_jobs.id"), unique=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    title: Mapped[str] = mapped_column(String)
    due_at: Mapped[str] = mapped_column(String)
    read_at: Mapped[str | None] = mapped_column(String)


class DailyReview(Record, Base):
    __tablename__ = "daily_reviews"
    date: Mapped[str] = mapped_column(String(10), unique=True)
    actual_minutes: Mapped[int] = mapped_column(Integer, default=0)
    energy_level: Mapped[int] = mapped_column(Integer, default=3)
    notes: Mapped[str] = mapped_column(Text, default="")
    project_minutes: Mapped[dict] = mapped_column(JSON, default=dict)
    completed_tasks: Mapped[list] = mapped_column(JSON, default=list)
    unfinished_tasks: Mapped[list] = mapped_column(JSON, default=list)


class Settings(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    timezone: Mapped[str] = mapped_column(String, default="Asia/Shanghai")
    day_start: Mapped[str] = mapped_column(String(5), default="09:00")

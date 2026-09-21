from datetime import date as Date
import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .schemas import ToolArguments


class DateRange(ToolArguments):
    date: str | None = None
    start_date: str | None = None
    end_date: str | None = None

    @field_validator("date", "start_date", "end_date")
    @classmethod
    def valid_date(cls, value):
        return Date.fromisoformat(value).isoformat() if value else value

    @model_validator(mode="after")
    def valid_range(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date 不能早于 start_date")
        return self


class EmptyArgs(ToolArguments):
    pass


class GetTasksArgs(DateRange):
    project_id: str | None = None
    status: Literal["pending", "completed", "overdue", "rescheduled", "cancelled"] | None = None


class GetCalendarArgs(DateRange):
    pass


class GetFreeSlotsArgs(ToolArguments):
    date: str
    earliest_time: str | None = None
    latest_time: str | None = None
    min_duration_minutes: int = Field(default=30, ge=1, le=1440)

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        return Date.fromisoformat(value).isoformat()

    @field_validator("earliest_time", "latest_time")
    @classmethod
    def valid_time(cls, value):
        if value and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("时间必须为 HH:MM")
        return value


class UpcomingArgs(ToolArguments):
    days: int = Field(default=14, ge=1, le=365)


class CreateTaskArgs(ToolArguments):
    title: str = Field(min_length=1, max_length=200)
    date: str
    start_time: str | None = Field(default=None, description="任务开始时间，格式 HH:MM；字段名必须是 start_time")
    end_time: str | None = Field(default=None, description="任务结束时间，格式 HH:MM；字段名必须是 end_time")
    duration_minutes: int = Field(default=30, ge=1, le=1440)
    project_id: str | None = None
    priority: int = Field(default=2, ge=1, le=3)
    description: str = Field(default="", max_length=10000)

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        return Date.fromisoformat(value).isoformat()

    @field_validator("start_time", "end_time")
    @classmethod
    def valid_time(cls, value):
        if value and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("时间必须为 HH:MM")
        return value


class UpdateTaskArgs(ToolArguments):
    task_id: str
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    project_id: str | None = None
    priority: int | None = Field(default=None, ge=1, le=3)

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        return Date.fromisoformat(value).isoformat() if value else value

    @field_validator("start_time", "end_time")
    @classmethod
    def valid_time(cls, value):
        if value and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("时间必须为 HH:MM")
        return value


class RescheduleTaskArgs(ToolArguments):
    task_id: str
    new_date: str
    new_start_time: str | None = None
    new_end_time: str | None = None

    @field_validator("new_date")
    @classmethod
    def valid_date(cls, value):
        return Date.fromisoformat(value).isoformat()

    @field_validator("new_start_time", "new_end_time")
    @classmethod
    def valid_time(cls, value):
        if value and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("时间必须为 HH:MM")
        return value


class TaskIdArgs(ToolArguments):
    task_id: str


class CreateRoutineArgs(ToolArguments):
    name: str = Field(min_length=1, max_length=200)
    frequency: Literal["daily", "every_n_days", "weekly", "weekdays", "custom"]
    interval: int = Field(default=1, ge=1, le=365)
    weekdays: list[int] = Field(default_factory=list)
    start_date: str
    end_date: str | None = None
    preferred_time: str | None = None
    estimated_duration: int = Field(default=30, ge=1, le=1440)
    priority: int = Field(default=2, ge=1, le=3)
    project_id: str | None = None
    description: str = Field(default="", max_length=10000)

    @field_validator("start_date", "end_date")
    @classmethod
    def valid_date(cls, value):
        return Date.fromisoformat(value).isoformat() if value else value

    @field_validator("preferred_time")
    @classmethod
    def valid_time(cls, value):
        if value and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("时间必须为 HH:MM")
        return value


class UpdateRoutineArgs(ToolArguments):
    routine_id: str
    name: str | None = Field(default=None, min_length=1, max_length=200)
    preferred_time: str | None = None
    estimated_duration: int | None = Field(default=None, ge=1, le=1440)
    priority: int | None = Field(default=None, ge=1, le=3)
    end_date: str | None = None

    @field_validator("end_date")
    @classmethod
    def valid_date(cls, value):
        return Date.fromisoformat(value).isoformat() if value else value

    @field_validator("preferred_time")
    @classmethod
    def valid_time(cls, value):
        if value and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("时间必须为 HH:MM")
        return value


class RoutineIdArgs(ToolArguments):
    routine_id: str


class ScheduleTaskArgs(ToolArguments):
    title: str = Field(min_length=1, max_length=200)
    date: str
    duration_minutes: int = Field(ge=1, le=1440)
    preferred_period: Literal["morning", "afternoon", "evening"] | None = None
    earliest_time: str | None = None
    latest_time: str | None = None
    project_id: str | None = None

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        return Date.fromisoformat(value).isoformat()

    @field_validator("earliest_time", "latest_time")
    @classmethod
    def valid_time(cls, value):
        if value and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("时间必须为 HH:MM")
        return value


class ReplanDayArgs(ToolArguments):
    date: str
    blocked_start: str | None = None
    blocked_end: str | None = None

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        return Date.fromisoformat(value).isoformat()

    @field_validator("blocked_start", "blocked_end")
    @classmethod
    def valid_time(cls, value):
        if value and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("时间必须为 HH:MM")
        return value


class DeleteTaskArgs(TaskIdArgs):
    description: str = "删除指定任务"


class ConfirmArgs(ToolArguments):
    action_id: str

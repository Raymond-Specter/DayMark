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
    milestone_id: str | None = None
    priority: int = Field(default=2, ge=1, le=3)
    description: str = Field(default="", max_length=10000)
    deadline: str | None = None
    reminder: Literal[0, 10, 30, 60, 1440] | None = None
    depends_on_task_id: str | None = None
    track_learning: bool = False

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
    milestone_id: str | None = None
    priority: int | None = Field(default=None, ge=1, le=3)
    deadline: str | None = None
    reminder: Literal[0, 10, 30, 60, 1440] | None = None
    depends_on_task_id: str | None = None
    track_learning: bool | None = None

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
    interval_unit: Literal["days", "weeks"] = "days"
    weekdays: list[int] = Field(default_factory=list)
    start_date: str
    end_date: str | None = None
    preferred_time: str | None = None
    estimated_duration: int = Field(default=30, ge=1, le=1440)
    priority: int = Field(default=2, ge=1, le=3)
    project_id: str | None = None
    milestone_id: str | None = None
    reminder: Literal[0, 10, 30, 60, 1440] | None = None
    active: bool = True
    depends_on_routine_id: str | None = None
    offset_days: int = Field(default=0, ge=0, le=365)
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


class TimetableCourse(ToolArguments):
    name: str = Field(min_length=1, max_length=200)
    weekdays: list[Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]] = Field(
        min_length=1, max_length=7, description="上课星期，必须使用英文小写全称")
    start_time: str = Field(description="上课时间 HH:MM")
    end_time: str = Field(description="下课时间 HH:MM")
    location: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=1000)

    @field_validator("weekdays")
    @classmethod
    def valid_weekdays(cls, value):
        order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        return sorted(set(value), key=order.index)

    @field_validator("start_time", "end_time")
    @classmethod
    def valid_course_time(cls, value):
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("时间必须为 HH:MM")
        return value

    @model_validator(mode="after")
    def valid_period(self):
        if self.end_time <= self.start_time:
            raise ValueError("下课时间必须晚于上课时间")
        return self


class ImportTimetableArgs(ToolArguments):
    start_date: str = Field(description="学期或课表生效日期 YYYY-MM-DD")
    end_date: str = Field(description="学期或课表结束日期 YYYY-MM-DD")
    courses: list[TimetableCourse] = Field(min_length=1, max_length=40)

    @field_validator("start_date", "end_date")
    @classmethod
    def valid_timetable_date(cls, value):
        return Date.fromisoformat(value).isoformat()

    @model_validator(mode="after")
    def valid_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        return self


class UpdateRoutineArgs(ToolArguments):
    routine_id: str
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    project_id: str | None = None
    milestone_id: str | None = None
    frequency: Literal["daily", "every_n_days", "weekly", "weekdays", "custom"] | None = None
    interval: int | None = Field(default=None, ge=1, le=365)
    interval_unit: Literal["days", "weeks"] | None = None
    weekdays: list[int] | None = None
    start_date: str | None = None
    preferred_time: str | None = None
    estimated_duration: int | None = Field(default=None, ge=1, le=1440)
    priority: int | None = Field(default=None, ge=1, le=3)
    reminder: Literal[0, 10, 30, 60, 1440] | None = None
    active: bool | None = None
    depends_on_routine_id: str | None = None
    offset_days: int | None = Field(default=None, ge=0, le=365)
    end_date: str | None = None

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


Status = Literal["active", "paused", "completed", "archived"]
EntryType = Literal["study", "assignment", "project", "output", "reading", "research", "internship", "exam", "reflection", "other"]
EntryStatus = Literal["in_progress", "completed", "partial", "abandoned"]
DocumentType = Literal["note", "slides", "assignment", "solution", "code", "paper", "output", "reflection", "reference", "exam", "other"]


class RecordIdArgs(ToolArguments):
    record_id: str


class GetOrganizationArgs(ToolArguments):
    status: Status | None = None


class CreateGoalArgs(ToolArguments):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    start_date: str | None = None
    target_date: str | None = None
    status: Status = "active"
    priority: int = Field(default=2, ge=1, le=3)
    color: str = Field(default="#4f6ef7", pattern=r"^#[0-9a-fA-F]{6}$")

    _dates = field_validator("start_date", "target_date")(lambda value: Date.fromisoformat(value).isoformat() if value else value)


class UpdateGoalArgs(CreateGoalArgs):
    record_id: str
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    status: Status | None = None
    priority: int | None = Field(default=None, ge=1, le=3)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class CreateProjectArgs(ToolArguments):
    name: str = Field(min_length=1, max_length=200)
    goal_id: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    status: Status = "active"
    description: str = Field(default="", max_length=10000)

    _dates = field_validator("start_date", "end_date")(lambda value: Date.fromisoformat(value).isoformat() if value else value)


class UpdateProjectArgs(CreateProjectArgs):
    record_id: str
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: Status | None = None
    description: str | None = Field(default=None, max_length=10000)


class CreateMilestoneArgs(ToolArguments):
    name: str = Field(min_length=1, max_length=200)
    project_id: str
    start_date: str | None = None
    deadline: str | None = None
    status: Status = "active"
    description: str = Field(default="", max_length=10000)

    _dates = field_validator("start_date", "deadline")(lambda value: Date.fromisoformat(value).isoformat() if value else value)


class UpdateMilestoneArgs(CreateMilestoneArgs):
    record_id: str
    name: str | None = Field(default=None, min_length=1, max_length=200)
    project_id: str | None = None
    status: Status | None = None
    description: str | None = Field(default=None, max_length=10000)


class EventIdArgs(ToolArguments):
    event_id: str


class CreateEventArgs(ToolArguments):
    title: str = Field(min_length=1, max_length=200)
    start: str
    end: str
    all_day: bool = False
    description: str = Field(default="", max_length=10000)
    color: str = Field(default="#4f6ef7", pattern=r"^#[0-9a-fA-F]{6}$")


class UpdateEventArgs(CreateEventArgs):
    event_id: str
    title: str | None = Field(default=None, min_length=1, max_length=200)
    start: str | None = None
    end: str | None = None
    all_day: bool | None = None
    description: str | None = Field(default=None, max_length=10000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class GetLearningEntriesArgs(DateRange):
    project_id: str | None = None
    entry_type: EntryType | None = None
    status: EntryStatus | None = None


class CreateLearningEntryArgs(ToolArguments):
    date: str
    title: str = Field(min_length=1, max_length=200)
    project_id: str | None = None
    task_id: str | None = None
    entry_type: EntryType = "study"
    description: str = Field(default="", max_length=50000)
    duration_minutes: int = Field(default=0, ge=0, le=10080)
    progress: int | None = Field(default=None, ge=0, le=100)
    status: EntryStatus = "completed"
    reflection: str = Field(default="", max_length=50000)
    problems: str = Field(default="", max_length=50000)
    next_action: str = Field(default="", max_length=10000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    concepts: list[str] = Field(default_factory=list, max_length=100)

    _date = field_validator("date")(lambda value: Date.fromisoformat(value).isoformat())


class UpdateLearningEntryArgs(CreateLearningEntryArgs):
    record_id: str
    date: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    entry_type: EntryType | None = None
    description: str | None = Field(default=None, max_length=50000)
    duration_minutes: int | None = Field(default=None, ge=0, le=10080)
    status: EntryStatus | None = None
    reflection: str | None = Field(default=None, max_length=50000)
    problems: str | None = Field(default=None, max_length=50000)
    next_action: str | None = Field(default=None, max_length=10000)
    tags: list[str] | None = Field(default=None, max_length=50)
    concepts: list[str] | None = Field(default=None, max_length=100)


class GetDocumentsArgs(DateRange):
    project_id: str | None = None
    document_type: DocumentType | None = None
    is_output: bool | None = None


class SaveAttachmentArgs(ToolArguments):
    filename: str = Field(min_length=1, max_length=200)
    knowledge_date: str
    title: str = Field(default="", max_length=200)
    project_id: str | None = None
    document_type: DocumentType = "other"
    is_output: bool = False
    description: str = Field(default="", max_length=20000)

    _date = field_validator("knowledge_date")(lambda value: Date.fromisoformat(value).isoformat())


class UpdateDocumentArgs(ToolArguments):
    record_id: str
    title: str | None = Field(default=None, min_length=1, max_length=200)
    knowledge_date: str | None = None
    project_id: str | None = None
    document_type: DocumentType | None = None
    is_output: bool | None = None
    description: str | None = Field(default=None, max_length=20000)

    _date = field_validator("knowledge_date")(lambda value: Date.fromisoformat(value).isoformat() if value else value)


class ReviewArgs(ToolArguments):
    date: str

    _date = field_validator("date")(lambda value: Date.fromisoformat(value).isoformat())


class SaveReviewArgs(ReviewArgs):
    actual_minutes: int = Field(default=0, ge=0, le=1440)
    energy_level: int = Field(default=3, ge=1, le=5)
    notes: str = Field(default="", max_length=20000)
    project_minutes: dict[str, int] = Field(default_factory=dict)


class StatisticsArgs(DateRange):
    pass


class UpdateSettingsArgs(ToolArguments):
    timezone: str | None = None
    day_start: str | None = None


class NotificationIdArgs(ToolArguments):
    notification_id: str


class UpdateAISettingsArgs(ToolArguments):
    mode: Literal["auto", "deepseek", "local"] | None = None
    model: str | None = Field(default=None, min_length=1, max_length=200,
                              pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_./:-]*$")
    num_ctx: int | None = Field(default=None, ge=2048, le=8192)
    temperature: float | None = Field(default=None, ge=0, le=2)
    think: bool | None = None

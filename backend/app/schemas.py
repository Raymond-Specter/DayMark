import re
from datetime import date as Date, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def check_dates(cls, value, info):
        if value is not None and (info.field_name in {"date", "start_date", "target_date", "end_date", "occurrence_date"}):
            if not isinstance(value, str):
                raise ValueError("日期必须为 YYYY-MM-DD 字符串")
            value = Date.fromisoformat(value).isoformat()
        if value is not None and info.field_name in {"start_time", "end_time", "preferred_time", "day_start"}:
            if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
                raise ValueError("时间必须为 HH:MM")
        return value


class Organization(Input):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    start_date: str | None = None
    status: Literal["active", "paused", "completed", "archived"] = "active"

    @model_validator(mode="after")
    def date_order(self):
        end = getattr(self, "target_date", None) or getattr(self, "end_date", None) or getattr(self, "deadline", None)
        if self.start_date and end and end < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        return self


class GoalIn(Organization):
    target_date: str | None = None
    priority: int = Field(default=2, ge=1, le=3)
    color: str = Field(default="#4f6ef7", pattern=r"^#[0-9a-fA-F]{6}$")


class ProjectIn(Organization):
    goal_id: str | None = None
    end_date: str | None = None


class MilestoneIn(Organization):
    project_id: str
    deadline: str | None = None

    @field_validator("deadline")
    @classmethod
    def deadline_date(cls, value):
        if value:
            Date.fromisoformat(value)
        return value


class TaskIn(Input):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    project_id: str | None = None
    milestone_id: str | None = None
    date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    deadline: str | None = None
    estimated_duration: int = Field(default=30, ge=0, le=1440)
    priority: int = Field(default=2, ge=1, le=3)
    depends_on_task_id: str | None = None
    reminder: Literal[0, 10, 30, 60, 1440] | None = None
    track_learning: bool = False
    version: int | None = None

    @field_validator("deadline")
    @classmethod
    def normalize_deadline(cls, value):
        if value:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                raise ValueError("截止时间必须包含时区")
            from datetime import timezone
            return dt.astimezone(timezone.utc).isoformat()
        return value

    @model_validator(mode="after")
    def times(self):
        if (self.start_time or self.end_time) and not self.date:
            raise ValueError("设置时间前必须选择日期")
        if self.end_time and (not self.start_time or self.end_time <= self.start_time):
            raise ValueError("结束时间必须晚于开始时间；跨天请拆成两个任务")
        if self.start_time and not self.end_time:
            h, m = map(int, self.start_time.split(":"))
            if h * 60 + m + max(15, self.estimated_duration) >= 1440:
                raise ValueError("自动计算的结束时间超过当天，请调整开始时间或时长")
        if self.reminder is not None and not (self.date or self.deadline):
            raise ValueError("提醒需要计划日期或截止时间")
        return self


class RoutineIn(Input):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    project_id: str | None = None
    milestone_id: str | None = None
    frequency: Literal["daily", "every_n_days", "weekly", "weekdays", "custom"] = "daily"
    interval: int = Field(default=1, ge=1, le=365)
    interval_unit: Literal["days", "weeks"] = "days"
    weekdays: list[int] = Field(default_factory=list)
    start_date: str
    end_date: str | None = None
    preferred_time: str | None = None
    estimated_duration: int = Field(default=30, ge=1, le=1440)
    priority: int = Field(default=2, ge=1, le=3)
    reminder: Literal[0, 10, 30, 60, 1440] | None = None
    active: bool = True
    depends_on_routine_id: str | None = None
    offset_days: int = Field(default=0, ge=0, le=365)
    version: int | None = None

    @model_validator(mode="after")
    def validate_rule(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        if any(day < 0 or day > 6 for day in self.weekdays):
            raise ValueError("星期应为 0（周一）至 6（周日）")
        self.weekdays = sorted(set(self.weekdays))
        if self.frequency == "weekdays" and not self.weekdays:
            raise ValueError("至少选择一个星期")
        if self.preferred_time:
            h, m = map(int, self.preferred_time.split(":"))
            if h * 60 + m + self.estimated_duration >= 1440:
                raise ValueError("任务不能跨过午夜，请缩短时长或提前开始")
        return self


class TaskAction(Input):
    action: Literal["complete", "reopen", "reschedule", "cancel", "keep_overdue"]
    date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    version: int


class EventIn(Input):
    title: str = Field(min_length=1, max_length=200)
    start: str
    end: str
    all_day: bool = False
    description: str = Field(default="", max_length=10000)
    color: str = Field(default="#4f6ef7", pattern=r"^#[0-9a-fA-F]{6}$")

    @model_validator(mode="after")
    def bounds(self):
        if self.all_day:
            begin, end = Date.fromisoformat(self.start), Date.fromisoformat(self.end)
        else:
            begin, end = datetime.fromisoformat(self.start), datetime.fromisoformat(self.end)
            if begin.tzinfo or end.tzinfo:
                raise ValueError("日历事件使用设置中的本地时间，不带时区偏移")
        if end <= begin:
            raise ValueError("结束时间必须晚于开始时间")
        return self


class ReviewIn(Input):
    actual_minutes: int = Field(default=0, ge=0, le=1440)
    energy_level: int = Field(default=3, ge=1, le=5)
    notes: str = Field(default="", max_length=20000)
    project_minutes: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def allocation(self):
        if any(minutes < 0 for minutes in self.project_minutes.values()) or sum(self.project_minutes.values()) > self.actual_minutes:
            raise ValueError("项目时间不能为负，合计不能超过实际总时间")
        return self


class SettingsIn(Input):
    timezone: str = "Asia/Shanghai"
    day_start: str = "09:00"

    @field_validator("timezone")
    @classmethod
    def timezone_valid(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("请输入有效的 IANA 时区")
        return value

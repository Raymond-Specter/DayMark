from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EntryType = Literal["study", "assignment", "project", "output", "reading", "research", "internship", "exam", "reflection", "other"]
EntryStatus = Literal["in_progress", "completed", "partial", "abandoned"]
DocumentType = Literal["note", "slides", "assignment", "solution", "code", "paper", "output", "reflection", "reference", "exam", "other"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("date", "knowledge_date", check_fields=False)
    @classmethod
    def valid_date(cls, value):
        return date.fromisoformat(value).isoformat() if value else value


class LearningEntryIn(Input):
    date: str
    project_id: str | None = None
    task_id: str | None = None
    title: str = Field(min_length=1, max_length=200)
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


class LearningEntryPatch(Input):
    version: int = Field(ge=1)
    date: str | None = None
    project_id: str | None = None
    task_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    entry_type: EntryType | None = None
    description: str | None = Field(default=None, max_length=50000)
    duration_minutes: int | None = Field(default=None, ge=0, le=10080)
    progress: int | None = Field(default=None, ge=0, le=100)
    status: EntryStatus | None = None
    reflection: str | None = Field(default=None, max_length=50000)
    problems: str | None = Field(default=None, max_length=50000)
    next_action: str | None = Field(default=None, max_length=10000)
    tags: list[str] | None = Field(default=None, max_length=50)
    concepts: list[str] | None = Field(default=None, max_length=100)


class DocumentPatch(Input):
    version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    knowledge_date: str | None = None
    project_id: str | None = None
    document_type: DocumentType | None = None
    is_output: bool | None = None
    description: str | None = Field(default=None, max_length=20000)


class DocumentLinkIn(Input):
    relationship: Literal["evidence", "output", "reference"] = "evidence"

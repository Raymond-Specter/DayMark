from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ToolResult(BaseModel):
    success: bool
    message: str
    data: Any = None
    affected_entities: list[dict] = Field(default_factory=list)
    error_code: str | None = None
    confirmation: dict | None = None


class AgentOutcome(BaseModel):
    content: str
    metrics: dict = Field(default_factory=dict)
    affected_entities: list[dict] = Field(default_factory=list)
    confirmation: dict | None = None

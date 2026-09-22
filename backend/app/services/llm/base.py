from dataclasses import dataclass, field
from typing import AsyncIterator, Literal, Protocol


class LLMError(Exception):
    def __init__(self, code: str, message: str, status: int = 503):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


@dataclass
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    tool_call_id: str | None = None
    reasoning_content: str | None = None
    provider_metadata: dict = field(default_factory=dict)


@dataclass
class GenerationOptions:
    model: str = "qwen3:8b"
    num_ctx: int = 8192
    temperature: float = 0.6
    think: bool = False
    timeout: float = 180


@dataclass
class ChatChunk:
    content: str = ""
    done: bool = False
    tool_calls: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    reasoning_content: str = ""


class LLMProvider(Protocol):
    async def chat(self, messages: list[Message], options: GenerationOptions, tools: list[dict] | None = None) -> ChatChunk: ...
    def stream_chat(self, messages: list[Message], options: GenerationOptions, tools: list[dict] | None = None) -> AsyncIterator[ChatChunk]: ...
    async def health_check(self) -> bool: ...
    async def list_models(self) -> list[dict]: ...

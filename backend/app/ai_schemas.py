from pydantic import BaseModel, ConfigDict, Field, SecretStr


class AIInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ModelSettings(AIInput):
    mode: str = Field(default="auto", pattern=r"^(auto|deepseek|local)$")
    model: str = Field(default="qwen3:8b", min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_./:-]*$")
    num_ctx: int = Field(default=8192, ge=2048, le=8192)
    temperature: float = Field(default=0.6, ge=0, le=2)
    think: bool = False


class DeepSeekKeyIn(AIInput):
    api_key: SecretStr = Field(min_length=8, max_length=500)


class ConversationIn(AIInput):
    title: str = Field(default="新对话", min_length=1, max_length=200)


class ChatIn(AIInput):
    conversation_id: str = Field(min_length=1, max_length=36)
    message: str = Field(min_length=1, max_length=12000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=3)
    stream: bool = True


class ConfirmationIn(AIInput):
    conversation_id: str = Field(min_length=1, max_length=36)
    approve: bool

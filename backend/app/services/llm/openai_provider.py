from .base import LLMError


class OpenAIProvider:
    """Reserved adapter. No credentials or network requests in this release."""
    async def health_check(self):
        return False

    async def list_models(self):
        raise LLMError("not_configured", "OpenAI Provider 尚未实现。")

    async def chat(self, messages, options, tools=None):
        raise LLMError("not_configured", "OpenAI Provider 尚未实现。")

    async def stream_chat(self, messages, options, tools=None):
        raise LLMError("not_configured", "OpenAI Provider 尚未实现。")
        yield  # Make this placeholder an async iterator matching the protocol.

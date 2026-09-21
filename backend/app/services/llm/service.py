from .base import LLMProvider


class LLMService:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def health(self, model: str):
        from .base import LLMError
        try:
            models = await self.provider.list_models()
            available = any(m["name"] == model for m in models)
            return {"ollama_available": True, "model_available": available, "model": model,
                    "error": None if available else "所选模型未安装，请运行模型下载脚本。"}
        except LLMError as error:
            return {"ollama_available": False, "model_available": False, "model": model, "error": error.message}

    async def list_models(self):
        return await self.provider.list_models()

    def stream_chat(self, messages, options, tools=None):
        return self.provider.stream_chat(messages, options, tools)

    async def chat(self, messages, options, tools=None):
        return await self.provider.chat(messages, options, tools)

from dataclasses import replace

from .base import LLMError
from .service import LLMService


RECOVERABLE = {"not_configured", "timeout", "offline", "provider_unavailable", "rate_limited"}


class ProviderSession:
    def __init__(self, router, mode, options):
        self.router, self.mode = router, mode
        self.fell_back = False
        if mode == "local":
            self.name, self.service = "local", router.local
            self.options = replace(options, model=router.config.model, timeout=router.config.timeout)
        else:
            self.name, self.service = "deepseek", router.deepseek
            self.options = replace(options, model=router.config.deepseek_model, timeout=router.config.deepseek_timeout)

    def stream_chat(self, messages, tools=None):
        return self.service.stream_chat(messages, self.options, tools)

    def try_fallback(self, error, successful_write):
        if self.mode != "auto" or self.name != "deepseek" or successful_write or error.code not in RECOVERABLE:
            return False
        self.name, self.service, self.fell_back = "local", self.router.local, True
        self.options = replace(self.options, model=self.router.config.model, timeout=self.router.config.timeout)
        return True


class ProviderRouter:
    def __init__(self, deepseek_provider, local_provider, config):
        self.deepseek = LLMService(deepseek_provider)
        self.local = LLMService(local_provider)
        self.config = config

    def create_session(self, mode, options):
        return ProviderSession(self, mode, options)

    async def status(self, local_model):
        deepseek = {"configured": bool(self.config.deepseek_api_key), "online": False,
                    "model": self.config.deepseek_model, "error": None}
        if deepseek["configured"]:
            try:
                await self.deepseek.list_models()
                deepseek["online"] = True
            except LLMError as error:
                deepseek["error"] = error.message
        local = await self.local.health(local_model)
        return {
            "deepseek": deepseek,
            "local": {"configured": True, "online": local["ollama_available"],
                      "model_available": local["model_available"], "model": local_model,
                      "error": local["error"]},
        }

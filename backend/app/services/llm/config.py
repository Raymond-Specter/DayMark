import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


def load_env():
    # Explicit KEY=VALUE only: never execute a .env file as a shell script.
    path = Path(__file__).resolve().parents[4] / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, separator, value = line.strip().partition("=")
            if separator and key.startswith(("OLLAMA_", "DEEPSEEK_", "LLM_")):
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env_value(name, default):
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


@dataclass
class LLMConfig:
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen3:8b"
    num_ctx: int = 8192
    think: bool = False
    temperature: float = 0.6
    timeout: float = 180
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_timeout: float = 120
    deepseek_think_default: bool = False
    default_mode: str = "auto"

    @classmethod
    def from_env(cls):
        load_env()
        config = cls(
            base_url=env_value("OLLAMA_BASE_URL", cls.base_url).rstrip("/"),
            model=env_value("OLLAMA_MODEL", cls.model),
            num_ctx=int(env_value("OLLAMA_CONTEXT_LENGTH", "8192")),
            think=env_value("OLLAMA_THINK", "false").lower() == "true",
            temperature=float(env_value("OLLAMA_TEMPERATURE", "0.6")),
            timeout=float(env_value("OLLAMA_TIMEOUT", "180")),
            deepseek_api_key=env_value("DEEPSEEK_API_KEY", ""),
            deepseek_base_url=env_value("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            deepseek_model=env_value("DEEPSEEK_MODEL", "deepseek-flash"),
            deepseek_timeout=float(env_value("DEEPSEEK_TIMEOUT_SECONDS", "120")),
            deepseek_think_default=env_value("DEEPSEEK_THINKING_DEFAULT", "false").lower() == "true",
            default_mode=env_value("LLM_DEFAULT_MODE", "auto").lower(),
        )
        parsed = urlparse(config.base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password:
            raise ValueError("OLLAMA_BASE_URL 必须为本机 HTTP 地址")
        if not 2048 <= config.num_ctx <= 8192 or not 0 <= config.temperature <= 2 or not 10 <= config.timeout <= 600:
            raise ValueError("模型参数超出范围：context 2048–8192，temperature 0–2，timeout 10–600")
        deepseek_url = urlparse(config.deepseek_base_url)
        if deepseek_url.scheme not in {"http", "https"} or not deepseek_url.hostname or deepseek_url.username or deepseek_url.password:
            raise ValueError("DEEPSEEK_BASE_URL 必须是有效的 HTTP(S) 地址且不能包含凭据")
        if config.default_mode not in {"auto", "deepseek", "local"}:
            raise ValueError("LLM_DEFAULT_MODE 必须是 auto、deepseek 或 local")
        if not 10 <= config.deepseek_timeout <= 600:
            raise ValueError("DEEPSEEK_TIMEOUT_SECONDS 必须在 10–600 之间")
        return config

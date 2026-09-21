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
            if separator and key.startswith(("OLLAMA_", "LLM_")):
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
        )
        parsed = urlparse(config.base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password:
            raise ValueError("OLLAMA_BASE_URL 必须为本机 HTTP 地址")
        if not 2048 <= config.num_ctx <= 8192 or not 0 <= config.temperature <= 2 or not 10 <= config.timeout <= 600:
            raise ValueError("模型参数超出范围：context 2048–8192，temperature 0–2，timeout 10–600")
        return config

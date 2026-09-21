import json
from dataclasses import asdict
from typing import AsyncIterator

import httpx

from .base import ChatChunk, GenerationOptions, LLMError, Message


class OllamaProvider:
    def __init__(self, base_url: str, transport=None):
        self.base_url, self.transport = base_url, transport

    def client(self, timeout=5):
        return httpx.AsyncClient(base_url=self.base_url, timeout=httpx.Timeout(timeout, connect=5), trust_env=False, transport=self.transport)

    def error(self, text: str, status=503):
        lowered = text.lower()
        if "not found" in lowered or status == 404:
            return LLMError("model_missing", "所选模型未安装，请运行 scripts/setup_ollama.ps1 -Start -Pull。", 503)
        if any(word in lowered for word in ("out of memory", "cuda error", "memory", "allocation")):
            return LLMError("model_memory", "模型加载失败或可用显存不足。请关闭其他占用 GPU 的程序，或降低上下文长度后重试。")
        return LLMError("model_failed", "Ollama 无法生成回答，请检查 logs/ollama.stderr.log 后重试。", 502)

    async def list_models(self):
        try:
            async with self.client() as client:
                response = await client.get("/api/tags")
                response.raise_for_status()
                return [{"name": m["name"], "size": m.get("size", 0)} for m in response.json()["models"]]
        except httpx.TimeoutException as error:
            raise LLMError("timeout", "Ollama 状态检查超时。") from error
        except httpx.HTTPError as error:
            raise LLMError("offline", "Ollama Offline：请启动项目内的 Ollama 服务。") from error
        except (ValueError, KeyError, TypeError) as error:
            raise LLMError("invalid_response", "Ollama 返回的模型列表格式无效。", 502) from error

    async def health_check(self):
        try:
            await self.list_models()
            return True
        except LLMError:
            return False

    async def stream_chat(self, messages: list[Message], options: GenerationOptions, tools=None) -> AsyncIterator[ChatChunk]:
        payload = {"model": options.model, "messages": [asdict(m) for m in messages], "stream": True,
                   "think": options.think, "keep_alive": "5m", "options": {
                       "num_ctx": options.num_ctx, "temperature": options.temperature, "num_predict": 2048}}
        if tools:
            payload["tools"] = tools
        finished = False
        try:
            async with self.client(options.timeout) as client:
                async with client.stream("POST", "/api/chat", json=payload) as response:
                    if response.status_code >= 400:
                        raise self.error((await response.aread()).decode(errors="replace"), response.status_code)
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        item = json.loads(line)
                        if item.get("error"):
                            raise self.error(str(item["error"]))
                        message = item.get("message", {})
                        # Deliberately discard the provider's separate thinking field.
                        finished = bool(item.get("done"))
                        yield ChatChunk(content=message.get("content", ""), done=finished,
                                        tool_calls=message.get("tool_calls", []),
                                        metrics={k: item[k] for k in ("eval_count", "prompt_eval_count", "total_duration", "done_reason") if k in item})
                        if finished:
                            break
            if not finished:
                raise LLMError("interrupted", "模型连接中断，已保留收到的部分回答。", 502)
        except httpx.TimeoutException as error:
            raise LLMError("timeout", "Ollama 响应超时，请稍后重试或降低上下文长度。", 504) from error
        except httpx.HTTPError as error:
            raise LLMError("offline", "Ollama 连接中断或未启动，已保留收到的内容。") from error
        except (ValueError, TypeError, KeyError) as error:
            raise LLMError("invalid_response", "模型返回了无法解析的数据。", 502) from error

    async def chat(self, messages, options, tools=None):
        result = ChatChunk()
        async for chunk in self.stream_chat(messages, options, tools):
            result.content += chunk.content
            result.tool_calls.extend(chunk.tool_calls)
            result.metrics.update(chunk.metrics)
            result.done = chunk.done
        return result

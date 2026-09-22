import json
from typing import AsyncIterator

import httpx

from .base import ChatChunk, GenerationOptions, LLMError, Message


class DeepSeekProvider:
    """OpenAI-compatible DeepSeek Chat Completions adapter."""

    def __init__(self, base_url: str, api_key: str, model: str = "deepseek-flash", transport=None):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.transport = transport

    def client(self, timeout=120):
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=httpx.Timeout(timeout, connect=10),
            # Windows users commonly reach cloud APIs through the system proxy.
            # httpx discovers that proxy through the environment/registry only
            # when trust_env is enabled; TLS verification remains enabled.
            trust_env=True,
            transport=self.transport,
        )

    def _configured(self):
        if not self.api_key:
            raise LLMError("not_configured", "DeepSeek API Key 未配置，请在项目 .env 中设置 DEEPSEEK_API_KEY。", 503)

    @staticmethod
    def _error(status: int, body: str):
        if status in {401, 403}:
            return LLMError("auth_failed", "DeepSeek 鉴权失败，请检查后端 .env 中的 API Key。", 401)
        if status == 429:
            return LLMError("rate_limited", "DeepSeek 请求过于频繁或额度不足，请稍后重试。", 429)
        if status >= 500:
            return LLMError("provider_unavailable", "DeepSeek 服务暂时不可用。", 503)
        return LLMError("invalid_request", f"DeepSeek 拒绝了请求（HTTP {status}）。", 502)

    @staticmethod
    def _message(message: Message):
        data = {"role": message.role, "content": message.content}
        if message.tool_calls:
            data["tool_calls"] = message.tool_calls
        if message.tool_call_id:
            data["tool_call_id"] = message.tool_call_id
        if message.role == "assistant" and message.reasoning_content is not None:
            data["reasoning_content"] = message.reasoning_content
        return data

    async def list_models(self):
        self._configured()
        try:
            async with self.client(15) as client:
                response = await client.get("/models")
                if response.status_code >= 400:
                    raise self._error(response.status_code, response.text)
                return [{"name": item["id"]} for item in response.json().get("data", [])]
        except LLMError:
            raise
        except httpx.TimeoutException as error:
            raise LLMError("timeout", "DeepSeek 状态检查超时。", 504) from error
        except httpx.HTTPError as error:
            raise LLMError("offline", "无法连接 DeepSeek 服务。", 503) from error
        except (ValueError, KeyError, TypeError) as error:
            raise LLMError("invalid_response", "DeepSeek 返回了无效的状态响应。", 502) from error

    async def health_check(self):
        try:
            await self.list_models()
            return True
        except LLMError:
            return False

    async def stream_chat(self, messages: list[Message], options: GenerationOptions, tools=None) -> AsyncIterator[ChatChunk]:
        self._configured()
        payload = {
            "model": self.model,
            "messages": [self._message(message) for message in messages],
            "stream": True,
            "thinking": {"type": "enabled" if options.think else "disabled"},
        }
        if not options.think:
            payload["temperature"] = options.temperature
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        tool_calls: dict[int, dict] = {}
        finished = False
        try:
            async with self.client(options.timeout) as client:
                async with client.stream("POST", "/chat/completions", json=payload) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode(errors="replace")
                        raise self._error(response.status_code, body)
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            finished = True
                            break
                        item = json.loads(data)
                        choice = (item.get("choices") or [{}])[0]
                        delta = choice.get("delta") or {}
                        for part in delta.get("tool_calls") or []:
                            index = int(part.get("index", 0))
                            current = tool_calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                            if part.get("id"):
                                current["id"] = part["id"]
                            function = part.get("function") or {}
                            current["function"]["name"] += function.get("name") or ""
                            current["function"]["arguments"] += function.get("arguments") or ""
                        metrics = {"provider": "deepseek", "model": item.get("model", self.model)}
                        if item.get("usage"):
                            metrics["usage"] = item["usage"]
                        yield ChatChunk(
                            content=delta.get("content") or "",
                            reasoning_content=delta.get("reasoning_content") or "",
                            done=choice.get("finish_reason") is not None,
                            metrics=metrics,
                        )
                        if choice.get("finish_reason") is not None:
                            finished = True
                    if tool_calls:
                        normalized = []
                        for _, call in sorted(tool_calls.items()):
                            arguments = call["function"]["arguments"]
                            try:
                                call["function"]["arguments"] = json.loads(arguments or "{}")
                            except json.JSONDecodeError:
                                pass
                            normalized.append(call)
                        yield ChatChunk(done=True, tool_calls=normalized, metrics={"provider": "deepseek", "model": self.model})
            if not finished:
                raise LLMError("interrupted", "DeepSeek 连接中断，已保留收到的部分回答。", 502)
        except LLMError:
            raise
        except httpx.TimeoutException as error:
            raise LLMError("timeout", "DeepSeek 响应超时。", 504) from error
        except httpx.HTTPError as error:
            raise LLMError("offline", "DeepSeek 连接中断。", 503) from error
        except (ValueError, TypeError, KeyError) as error:
            raise LLMError("invalid_response", "DeepSeek 返回了无法解析的数据。", 502) from error

    async def chat(self, messages, options, tools=None):
        result = ChatChunk()
        async for chunk in self.stream_chat(messages, options, tools):
            result.content += chunk.content
            result.reasoning_content += chunk.reasoning_content
            result.tool_calls.extend(chunk.tool_calls)
            result.metrics.update(chunk.metrics)
            result.done = result.done or chunk.done
        return result

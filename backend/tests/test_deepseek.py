import asyncio
import json

import httpx
import pytest

from app.services.llm.base import GenerationOptions, LLMError, Message
from app.services.llm.deepseek_provider import DeepSeekProvider
from app.services.llm.router import ProviderRouter
from app.services.llm.config import LLMConfig
from app.agent.agent_service import AgentService
from app.agent.registry import build_registry
from app.agent.tool_executor import ToolExecutor
from app.models import Conversation, Task
from sqlalchemy import select


def test_deepseek_streaming_tools_and_reasoning_round_trip():
    async def run():
        requests = []
        def handler(request):
            payload = json.loads(request.content)
            requests.append(payload)
            body = "\n".join([
                'data: {"model":"deepseek-flash","choices":[{"delta":{"reasoning_content":"private ","tool_calls":[{"index":0,"id":"call-1","type":"function","function":{"name":"create_","arguments":"{\\\"title\\\":\\\"A\\\""}}]},"finish_reason":null}]}',
                'data: {"model":"deepseek-flash","choices":[{"delta":{"reasoning_content":"thought","tool_calls":[{"index":0,"function":{"name":"task","arguments":"}"}}]},"finish_reason":"tool_calls"}]}',
                'data: [DONE]',
            ])
            return httpx.Response(200, text=body)
        provider = DeepSeekProvider("https://api.deepseek.com", "secret", transport=httpx.MockTransport(handler))
        result = await provider.chat([Message("user", "安排 A")], GenerationOptions(think=True), [{"type": "function", "function": {"name": "create_task"}}])
        assert result.reasoning_content == "private thought"
        assert result.tool_calls[0]["function"] == {"name": "create_task", "arguments": {"title": "A"}}
        assert requests[0]["tool_choice"] == "auto"
        assert requests[0]["thinking"] == {"type": "enabled"}
        followup = Message("assistant", "", result.tool_calls, reasoning_content=result.reasoning_content)
        await provider.chat([Message("user", "安排 A"), followup], GenerationOptions(think=True), [])
        assert requests[1]["messages"][1]["reasoning_content"] == "private thought"
    asyncio.run(run())


def test_deepseek_missing_key_is_explicit():
    async def run():
        provider = DeepSeekProvider("https://api.deepseek.com", "")
        with pytest.raises(LLMError) as error:
            await provider.chat([], GenerationOptions())
        assert error.value.code == "not_configured"
    asyncio.run(run())


def test_deepseek_client_honors_system_proxy(monkeypatch):
    options = {}

    class Client:
        def __init__(self, **kwargs):
            options.update(kwargs)

    monkeypatch.setattr("app.services.llm.deepseek_provider.httpx.AsyncClient", Client)
    DeepSeekProvider("https://api.deepseek.com", "secret").client()
    assert options["trust_env"] is True


def test_auto_fallback_only_before_write():
    class Broken:
        async def stream_chat(self, *_args, **_kwargs):
            raise LLMError("timeout", "timeout")
            yield
        async def list_models(self): return []
    class Local:
        async def stream_chat(self, *_args, **_kwargs):
            yield
        async def list_models(self): return [{"name": "qwen3:8b"}]
    config = LLMConfig(deepseek_api_key="x")
    route = ProviderRouter(Broken(), Local(), config).create_session("auto", GenerationOptions())
    assert route.name == "deepseek"
    assert route.try_fallback(LLMError("timeout", "timeout"), successful_write=False)
    assert route.name == "local"
    route = ProviderRouter(Broken(), Local(), config).create_session("auto", GenerationOptions())
    assert not route.try_fallback(LLMError("timeout", "timeout"), successful_write=True)


def test_agent_does_not_fallback_after_successful_write(session_factory):
    class DeepSeekScript:
        def __init__(self): self.count = 0
        async def stream_chat(self, *_args, **_kwargs):
            self.count += 1
            if self.count == 1:
                from app.services.llm.base import ChatChunk
                yield ChatChunk(tool_calls=[{"id": "1", "function": {"name": "create_task", "arguments": {
                    "title": "云端写入一次", "date": "2026-09-22", "start_time": "11:00", "duration_minutes": 30,
                }}}], done=True)
                return
            raise LLMError("timeout", "timeout")
            yield
        async def list_models(self): return [{"name": "deepseek-flash"}]
    class LocalShouldNotRun:
        def __init__(self): self.called = False
        async def stream_chat(self, *_args, **_kwargs):
            self.called = True
            yield
        async def list_models(self): return [{"name": "qwen3:8b"}]
    async def run():
        with session_factory() as db:
            conversation = Conversation(); db.add(conversation); db.commit(); key = conversation.id
        deep, local = DeepSeekScript(), LocalShouldNotRun()
        router = ProviderRouter(deep, local, LLMConfig(deepseek_api_key="x"))
        registry = build_registry()
        agent = AgentService(router, registry, ToolExecutor(registry, session_factory), session_factory)
        outcome = await agent.run(key, [Message("system", "test"), Message("user", "创建一个任务")],
                                  GenerationOptions(), lambda _event: asyncio.sleep(0), mode="auto", request_id="write-1")
        assert "操作已经完成" in outcome.content and not local.called
        with session_factory() as db:
            assert len(list(db.scalars(select(Task).where(Task.title == "云端写入一次")))) == 1
    asyncio.run(run())

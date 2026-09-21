import asyncio
import io
import json
import zipfile

import httpx
import pytest
from sqlalchemy import select

from app.api.ai import get_service
from app.ai_schemas import ChatIn
from app.main import app
from app.models import ChatAttachment, ChatMessage, Conversation
from app.services import attachments as attachment_service
from app.services.attachments import extract_text
from app.services.conversation import ConversationService, build_context
from app.services.llm.base import ChatChunk, GenerationOptions, LLMError, Message
from app.services.llm.config import LLMConfig
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.service import LLMService
from app.agent.permissions import ToolPermission
from app.agent.registry import build_registry


class FakeProvider:
    def __init__(self):
        self.received = []
        self.fail = False
        self.slow = False
        self.closed = False

    async def list_models(self):
        if self.fail:
            raise LLMError("offline", "Ollama Offline")
        return [{"name": "qwen3:8b", "size": 1}]

    async def stream_chat(self, messages, options, tools=None):
        self.received.append(messages)
        if self.fail:
            raise LLMError("offline", "Ollama Offline")
        try:
            yield ChatChunk(content="你好，")
            if self.slow:
                await asyncio.sleep(30)
            yield ChatChunk(content="我是你的规划助手。", done=True)
        finally:
            self.closed = True


@pytest.fixture
def ai(client):
    provider = FakeProvider()
    service = ConversationService(LLMService(provider), LLMConfig())
    app.dependency_overrides[get_service] = lambda: service
    return provider, service


def conversation(client):
    response = client.post("/api/ai/conversations", json={})
    assert response.status_code == 201
    return response.json()["id"]


def test_stream_and_persistent_history(client, ai):
    key = conversation(client)
    response = client.post("/api/ai/chat", json={"conversation_id": key, "message": "你好"})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert [e["event"] for e in events] == ["start", "delta", "delta", "done"]
    detail = client.get(f"/api/ai/conversations/{key}").json()
    assert len(detail["messages"]) == 2
    assert detail["messages"][1]["content"] == "你好，我是你的规划助手。"
    assert detail["messages"][1]["status"] == "completed"
    assert detail["title"] == "你好"
    assert ai[1].active is None


def test_upload_attachment_is_visible_and_in_model_context(client, ai, session_factory, tmp_path, monkeypatch):
    monkeypatch.setattr(attachment_service, "UPLOAD_DIR", tmp_path / "uploads")
    key = conversation(client)
    uploaded = client.post(
        f"/api/ai/conversations/{key}/attachments?filename=plan.md",
        content="# Week plan\nFinish chapter 3",
        headers={"Content-Type": "text/markdown"},
    )
    assert uploaded.status_code == 201
    attachment = uploaded.json()
    assert attachment["filename"] == "plan.md" and attachment["size_bytes"] > 0
    result = client.post("/api/ai/chat", json={
        "conversation_id": key, "message": "总结附件", "attachment_ids": [attachment["id"]], "stream": False,
    })
    assert result.json()["status"] == "completed"
    assert "[附件：plan.md]" in ai[0].received[-1][-1].content
    assert "Finish chapter 3" in ai[0].received[-1][-1].content
    message = client.get(f"/api/ai/conversations/{key}").json()["messages"][0]
    assert message["content"] == "总结附件"
    assert message["attachments"][0]["id"] == attachment["id"]
    assert client.get(f"/api/ai/attachments/{attachment['id']}").content.startswith(b"# Week plan")
    assert client.delete(f"/api/ai/attachments/{attachment['id']}").status_code == 409
    assert client.delete(f"/api/ai/conversations/{key}").status_code == 200
    with session_factory() as db:
        assert not list(db.scalars(select(ChatAttachment)))
    assert not list((tmp_path / "uploads").glob("*"))


def test_attachment_validation(client, ai, tmp_path, monkeypatch):
    monkeypatch.setattr(attachment_service, "UPLOAD_DIR", tmp_path / "uploads")
    key = conversation(client)
    unsupported = client.post(
        f"/api/ai/conversations/{key}/attachments?filename=archive.exe", content=b"binary")
    assert unsupported.status_code == 415
    empty = client.post(f"/api/ai/conversations/{key}/attachments?filename=empty.txt", content=b"")
    assert empty.status_code == 422


def test_docx_attachment_text_extraction():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", """<?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body><w:p><w:r><w:t>Monday 09:00 Algorithms</w:t></w:r></w:p></w:body>
        </w:document>""")
    assert extract_text("schedule.docx", buffer.getvalue()) == "Monday 09:00 Algorithms"


def test_scanned_pdf_falls_back_to_local_ocr(monkeypatch):
    monkeypatch.setattr(attachment_service, "_find_command", lambda *_: None)
    monkeypatch.setattr(attachment_service, "_ocr_pdf", lambda *_: "OCR schedule Monday 09:00")
    assert attachment_service._extract_pdf(b"scanned-pdf") == "OCR schedule Monday 09:00"


def test_multiturn_system_once(client, ai):
    key = conversation(client)
    for text in ["今晚学托福", "明早有考试"]:
        result = client.post("/api/ai/chat", json={"conversation_id": key, "message": text, "stream": False})
        assert result.json()["status"] == "completed"
    assert [m.role for m in ai[0].received[-1]] == ["system", "user", "assistant", "user"]
    assert ai[0].received[-1][1].content == "今晚学托福"
    saved = client.get(f"/api/ai/conversations/{key}").json()["messages"]
    assert all(m["role"] != "system" for m in saved)


def test_offline_keeps_planner_healthy(client, ai):
    ai[0].fail = True
    assert client.get("/api/ai/health").json()["ollama_available"] is False
    key = conversation(client)
    result = client.post("/api/ai/chat", json={"conversation_id": key, "message": "你好", "stream": False}).json()
    assert result["status"] == "error"
    assert "Offline" in result["error"]
    assert client.get("/api/today").status_code == 200
    ai[0].fail = False
    assert client.get("/api/ai/health").json()["model_available"] is True


def test_delete_cascades_and_unknown_conversation(client, ai, session_factory):
    key = conversation(client)
    client.post("/api/ai/chat", json={"conversation_id": key, "message": "hi", "stream": False})
    assert client.delete(f"/api/ai/conversations/{key}").status_code == 200
    with session_factory() as db:
        assert not list(db.scalars(select(ChatMessage)))
    assert client.get(f"/api/ai/conversations/{key}").status_code == 404
    assert client.post("/api/ai/chat", json={"conversation_id": key, "message": "hi"}).status_code == 404


@pytest.mark.parametrize("payload", [{"num_ctx": 32768}, {"temperature": -1}, {"model": ""}, {"model": "test:cloud"}, {"unexpected": True}])
def test_invalid_settings(client, ai, payload):
    assert client.put("/api/ai/settings", json=payload).status_code == 422


def test_settings_persist_and_missing_model(client, ai):
    payload = {"model": "missing:8b", "num_ctx": 4096, "temperature": 0.8, "think": True}
    assert client.put("/api/ai/settings", json=payload).status_code == 200
    assert client.get("/api/ai/settings").json() == payload
    health = client.get("/api/ai/health").json()
    assert health["ollama_available"] and not health["model_available"]


def test_stop_saves_partial_and_releases_single_slot(session_factory):
    async def run():
        provider = FakeProvider()
        provider.slow = True
        service = ConversationService(LLMService(provider), LLMConfig())
        with session_factory() as db:
            row = Conversation()
            db.add(row); db.commit()
            payload = ChatIn(conversation_id=row.id, message="hello")
            active = service.start(db, payload)
            with pytest.raises(Exception) as error:
                service.start(db, payload)
            assert error.value.status_code == 409
            await active.queue.get()
            delta = await active.queue.get()
            assert delta["event"] == "delta"
            assert await service.stop(row.id)
            db.expire_all()
            answer = db.get(ChatMessage, active.message_id)
            assert answer.status == "stopped" and answer.content == "你好，"
            assert provider.closed and service.active is None
            provider.slow = False
            second = service.start(db, payload)
            await second.task
            assert second.result["status"] == "completed"
    asyncio.run(run())


def test_immediate_stop_releases_slot(session_factory):
    async def run():
        service = ConversationService(LLMService(FakeProvider()), LLMConfig())
        with session_factory() as db:
            row = Conversation(); db.add(row); db.commit()
            service.start(db, ChatIn(conversation_id=row.id, message="hi"))
            await service.stop(row.id)
            assert service.active is None
    asyncio.run(run())


def test_provider_stream_discards_thinking_and_sends_options():
    async def run():
        def handler(request):
            payload = json.loads(request.content)
            assert payload["think"] is False and payload["options"]["num_ctx"] == 8192
            return httpx.Response(200, content='{"message":{"thinking":"PRIVATE","content":"你好"},"done":false}\n{"message":{"content":"！"},"done":true}\n')
        provider = OllamaProvider("http://127.0.0.1:11434", httpx.MockTransport(handler))
        response = await provider.chat([Message("user", "hi")], GenerationOptions())
        assert response.content == "你好！" and "PRIVATE" not in str(response)
    asyncio.run(run())


@pytest.mark.parametrize("body,code", [('not found', 'model_missing'), ('CUDA out of memory', 'model_memory'), ('load failed', 'model_failed')])
def test_provider_errors(body, code):
    async def run():
        provider = OllamaProvider("http://127.0.0.1", httpx.MockTransport(lambda _: httpx.Response(500, text=body)))
        with pytest.raises(LLMError) as result:
            await provider.chat([], GenerationOptions())
        assert result.value.code == code
    asyncio.run(run())


def test_provider_rejects_truncated_stream():
    async def run():
        provider = OllamaProvider("http://127.0.0.1", httpx.MockTransport(lambda _: httpx.Response(200, text='{"message":{"content":"partial"}}\n')))
        with pytest.raises(LLMError, match="中断"):
            await provider.chat([], GenerationOptions())
    asyncio.run(run())


def test_tool_permission_boundary():
    registry = build_registry()
    assert registry.require("get_today_tasks").permission == ToolPermission.READ
    assert registry.require("create_task").permission == ToolPermission.WRITE
    assert registry.require("delete_task").permission == ToolPermission.DESTRUCTIVE


def test_context_budget_keeps_latest_full_pairs():
    rows = []
    for index in range(8):
        rows.extend([ChatMessage(role="user", content=f"问题{index}" + "字" * 800),
                     ChatMessage(role="assistant", content=f"回答{index}" + "字" * 800, status="completed")])
    context, trimmed = build_context(rows, "最新问题", GenerationOptions())
    assert trimmed
    assert context[0].role == "system" and context[-1].content == "最新问题"
    assert context[-2].content.startswith("回答7")
    assert [m.role for m in context[1:-1]] == ["user", "assistant"] * ((len(context) - 2) // 2)


def test_oversized_context_does_not_save_or_acquire_slot(client, ai):
    key = conversation(client)
    response = client.post("/api/ai/chat", json={"conversation_id": key, "message": "字" * 12000})
    assert response.status_code == 422
    assert client.get(f"/api/ai/conversations/{key}").json()["messages"] == []
    assert ai[1].active is None


def test_total_timeout_preserves_partial_and_closes_provider(session_factory):
    async def run():
        provider = FakeProvider(); provider.slow = True
        service = ConversationService(LLMService(provider), LLMConfig(timeout=0.03))
        with session_factory() as db:
            row = Conversation(); db.add(row); db.commit()
            active = service.start(db, ChatIn(conversation_id=row.id, message="hello"))
            await active.task
            assert active.result["status"] == "error"
            assert "总时限" in active.result["error"]
            assert active.result["content"] == "你好，"
            assert provider.closed and service.active is None
    asyncio.run(run())


def test_disconnect_closes_generation(session_factory):
    async def run():
        provider = FakeProvider(); provider.slow = True
        service = ConversationService(LLMService(provider), LLMConfig())
        with session_factory() as db:
            row = Conversation(); db.add(row); db.commit()
            active = service.start(db, ChatIn(conversation_id=row.id, message="hello"))
            events = service.events(active)
            await events.__anext__()
            await events.__anext__()
            await events.aclose()
            assert service.active is None and provider.closed
            assert active.result["status"] == "stopped"
    asyncio.run(run())


def test_simultaneous_stops_are_idempotent(session_factory):
    async def run():
        provider = FakeProvider(); provider.slow = True
        service = ConversationService(LLMService(provider), LLMConfig())
        with session_factory() as db:
            row = Conversation(); db.add(row); db.commit()
            active = service.start(db, ChatIn(conversation_id=row.id, message="hello"))
            await active.queue.get(); await active.queue.get()
            await asyncio.gather(service.stop(row.id), service.stop(row.id))
            assert service.active is None and active.result["status"] == "stopped"
    asyncio.run(run())


def test_partial_save_failure_is_visible(session_factory, monkeypatch):
    async def run():
        service = ConversationService(LLMService(FakeProvider()), LLMConfig())
        def fail(*_):
            raise RuntimeError("simulated disk failure")
        monkeypatch.setattr(service, "_save", fail)
        with session_factory() as db:
            row = Conversation(); db.add(row); db.commit()
            active = service.start(db, ChatIn(conversation_id=row.id, message="hello"))
            await active.task
            assert active.result["status"] == "error" and "数据库" in active.result["error"]
            assert service.active is None
    asyncio.run(run())


def test_provider_timeout():
    async def run():
        def fail(_):
            raise httpx.ReadTimeout("test")
        provider = OllamaProvider("http://127.0.0.1", httpx.MockTransport(fail))
        with pytest.raises(LLMError) as result:
            await provider.chat([], GenerationOptions())
        assert result.value.code == "timeout"
    asyncio.run(run())

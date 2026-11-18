"""Guest requests round-trip browser snapshots through real routes, without accounts."""
import asyncio
import base64
import json
import os
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import pytest
import httpx

from app import accounts, guest
from app.api.ai import tenant_services
from app.database import clear_tenant_factories
from app.main import app
from app.runtime import guest_context
from app.services.llm.base import ChatChunk

ORIGIN = "https://plan.example.com"


class Browser:
    def __init__(self, client):
        self.client = client
        self.state = {}
        self.frames = []

    def call(self, path, method="GET", data=None, content=None):
        payload = json.dumps(data).encode() if data is not None else (content or b"")
        response = self.client.post("/api/guest", json={
            "run_id": str(uuid4()), "path": "/api" + path, "method": method,
            "state": self.state, "body": base64.b64encode(payload).decode(),
        })
        assert response.status_code == 200, response.text
        self.frames = [json.loads(line) for line in response.text.splitlines()]
        assert not any(frame["kind"] == "error" for frame in self.frames), response.text
        for frame in self.frames:
            if frame["kind"] == "state":
                self.state.update(frame["state"])
        headers = next(frame for frame in self.frames if frame["kind"] == "response")
        body = b"".join(base64.b64decode(frame["data"]) for frame in self.frames if frame["kind"] == "body")
        return headers["status"], body

    def json(self, path, method="GET", data=None, status=200):
        code, body = self.call(path, method, data)
        assert code == status, body.decode()
        return json.loads(body)


@pytest.fixture
def browsers(monkeypatch, tmp_path):
    monkeypatch.setenv("DAYMARK_MODE", "cloud")
    monkeypatch.setenv("DAYMARK_DATA_DIR", str(tmp_path / "accounts"))
    monkeypatch.setenv("DAYMARK_PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("DAYMARK_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("DAYMARK_INVITE_CODE", "test-invitation-code-1234")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "server-secret-must-never-be-used")
    clear_tenant_factories()
    accounts.initialize()
    directories = []
    original = guest.GuestWorkspace.__init__

    def track(workspace):
        original(workspace)
        directories.append(workspace.directory)

    monkeypatch.setattr(guest.GuestWorkspace, "__init__", track)
    client = TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})
    yield Browser(client), Browser(client), tmp_path
    client.close()
    assert not guest.active_workspaces
    assert all(not path.exists() for path in directories)
    assert guest_context.get() is None
    tenant_services.clear()
    clear_tenant_factories()


def test_guest_planning_round_trip_and_account_isolation(browsers):
    a, b, path = browsers
    assert a.client.get("/api/tasks").status_code == 401
    goal = a.json("/goals", "POST", {"name": "Guest goal"}, 201)
    project = a.json("/projects", "POST", {"name": "Guest project", "goal_id": goal["id"]}, 201)
    task = a.json("/tasks", "POST", {"title": "Browser task", "project_id": project["id"],
                                      "date": "2026-11-20", "start_time": "14:00", "end_time": "15:00"}, 201)
    assert a.json("/tasks")[0]["id"] == task["id"]
    assert a.json("/bootstrap")["projects"][0]["name"] == "Guest project"
    assert a.json("/progress")["goals"][0]["id"] == goal["id"]
    assert a.json("/calendar?start=2026-11-20&end=2026-11-21")
    a.json("/settings", "PUT", {"timezone": "Asia/Shanghai", "day_start": "08:00"})
    a.json("/learning-entries", "POST", {"title": "Learning", "date": "2026-11-18", "duration_minutes": 30}, 201)
    a.json("/reviews/2026-11-17", "PUT", {"actual_minutes": 60, "notes": "Guest review", "project_minutes": {}})
    assert a.json("/export")["tables"]["tasks"][0]["id"] == task["id"]
    assert b.json("/tasks") == []
    assert b.json("/learning-entries") == []
    # Even with a signed-in account cookie, a guest request cannot use its data.
    registered = a.client.post("/api/auth/register", json={"username": "alice", "password": "test-password-123456",
                                                          "invite_code": "test-invitation-code-1234"})
    assert registered.status_code == 201
    assert a.client.get("/api/tasks").json() == []
    assert len(a.json("/tasks")) == 1
    with accounts.registry() as db:
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    assert len(list((path / "accounts" / "users").iterdir())) == 1


def test_guest_knowledge_and_chat_files_survive_browser_reload(browsers):
    a, b, path = browsers
    conversation = a.json("/ai/conversations", "POST", {}, 201)
    code, body = a.call(f"/ai/conversations/{conversation['id']}/attachments?filename=note.txt", "POST", content=b"Guest attachment")
    assert code == 201, body
    attachment = json.loads(body)
    code, body = a.call("/documents/upload?filename=lesson.txt&knowledge_date=2026-11-18", "POST", content=b"Guest knowledge")
    assert code == 201, body
    document = json.loads(body)
    assert len(a.state["files"]) == 2
    restored = Browser(a.client)
    restored.state = json.loads(json.dumps(a.state))
    assert restored.call(f"/ai/attachments/{attachment['id']}")[1] == b"Guest attachment"
    assert restored.call(f"/documents/{document['id']}/download")[1] == b"Guest knowledge"
    assert b.json(f"/documents/{document['id']}", status=404)["detail"]
    assert not (path / "accounts" / "users").exists()


def test_guest_key_and_agent_writes_use_only_browser_workspace(browsers, monkeypatch):
    a, b, path = browsers
    from app.services.llm.deepseek_provider import DeepSeekProvider

    async def fake_stream(provider, messages, options, tools=None):
        assert provider.api_key == "guest-personal-key"
        if messages[-1].role == "tool":
            yield ChatChunk(content="已创建任务。", done=True)
        else:
            yield ChatChunk(done=True, tool_calls=[{"id": "tool-1", "type": "function", "function": {
                "name": "create_task", "arguments": {"title": "Agent guest task", "date": "2026-11-20", "start_time": "10:00", "end_time": "11:00"}}}])

    monkeypatch.setattr(DeepSeekProvider, "stream_chat", fake_stream)
    assert b.json("/ai/settings")["mode"] == "deepseek"
    assert b.json("/ai/health")["providers"]["deepseek"]["configured"] is False
    a.json("/ai/providers/deepseek/key", "PUT", {"api_key": "guest-personal-key"})
    assert a.state["api_key"] == "guest-personal-key"
    assert not b.state.get("api_key")
    conversation = a.json("/ai/conversations", "POST", {}, 201)
    code, body = a.call("/ai/chat", "POST", {"conversation_id": conversation["id"], "message": "创建任务", "stream": True})
    assert code == 200
    assert '"event": "tool_result"' in body.decode()
    assert '"status": "completed"' in body.decode()
    assert a.json("/tasks")[0]["title"] == "Agent guest task"
    assert a.json(f"/ai/conversations/{conversation['id']}")["messages"][-1]["status"] == "completed"
    assert b.json("/tasks") == []
    assert not tenant_services
    assert os.environ["DEEPSEEK_API_KEY"] == "server-secret-must-never-be-used"
    with accounts.registry() as db:
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    assert not (path / "accounts" / "users").exists()


def test_guest_questions_and_confirmation_survive_separate_requests(browsers, monkeypatch):
    a, _, _ = browsers
    from app.services.llm.deepseek_provider import DeepSeekProvider
    tool = {"name": "ask_user", "arguments": {"context": "Planning", "questions": [
        {"id": "duration", "question": "How long?", "options": ["30 minutes", "60 minutes"]}]}}

    async def fake_stream(provider, messages, options, tools=None):
        yield ChatChunk(done=True, tool_calls=[{"id": "tool", "type": "function", "function": tool}])

    monkeypatch.setattr(DeepSeekProvider, "stream_chat", fake_stream)
    conversation = a.json("/ai/conversations", "POST", {}, 201)
    a.json("/ai/chat", "POST", {"conversation_id": conversation["id"], "message": "Help me plan", "stream": False})
    restored = a.json(f"/ai/conversations/{conversation['id']}")
    assert restored["clarification"]["questions"][0]["id"] == "duration"
    task = a.json("/tasks", "POST", {"title": "Delete after confirmation"}, 201)
    tool.update(name="delete_task", arguments={"task_id": task["id"]})
    a.json("/ai/chat", "POST", {"conversation_id": conversation["id"], "message": "Delete task", "stream": False})
    confirmation = a.json(f"/ai/conversations/{conversation['id']}")["confirmation"]
    assert confirmation["tool"] == "delete_task"
    assert len(a.json("/tasks")) == 1
    result = a.json(f"/ai/confirm/{confirmation['action_id']}", "POST", {"conversation_id": conversation["id"], "approve": True})
    assert result["success"]
    assert a.json("/tasks") == []


def test_guest_stop_saves_partial_chat_and_cleans_up(browsers, monkeypatch):
    a, _, _ = browsers
    from app.services.llm.deepseek_provider import DeepSeekProvider
    conversation = a.json("/ai/conversations", "POST", {}, 201)

    async def run():
        started = asyncio.Event()

        async def slow_stream(provider, messages, options, tools=None):
            yield ChatChunk(content="Partial answer")
            started.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(DeepSeekProvider, "stream_chat", slow_stream)
        run_id = str(uuid4())
        payload = {"path": "/api/ai/chat", "method": "POST", "state": a.state, "run_id": run_id,
                   "body": base64.b64encode(json.dumps({"conversation_id": conversation["id"], "message": "hello"}).encode()).decode()}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
            pending = asyncio.create_task(client.post("/api/guest", json=payload))
            await asyncio.wait_for(started.wait(), 5)
            stopped = await client.post("/api/guest/stop", json={"run_id": run_id})
            assert stopped.json()["stopped"]
            response = await asyncio.wait_for(pending, 5)
        frames = [json.loads(line) for line in response.text.splitlines()]
        for frame in frames:
            if frame["kind"] == "state":
                a.state.update(frame["state"])

    asyncio.run(run())
    messages = a.json(f"/ai/conversations/{conversation['id']}")["messages"]
    assert messages[-1]["status"] == "stopped"
    assert messages[-1]["content"] == "Partial answer"


@pytest.mark.parametrize("path", ["/api/auth/register", "/api/guest", "/api/../health", "https://evil.example/api/tasks", "/api/%2e%2e/tasks"])
def test_guest_cannot_bypass_account_or_path_boundaries(browsers, path):
    a, _, _ = browsers
    response = a.client.post("/api/guest", json={"path": path, "run_id": str(uuid4())})
    assert response.status_code == 403


def test_guest_rejects_bad_snapshots_and_cross_origin(browsers, monkeypatch):
    a, _, path = browsers
    base = {"path": "/api/tasks", "run_id": str(uuid4())}
    for state in [{"version": 99}, {"tables": {"accounts": []}}, {"files": {"../../escape.txt": "YQ=="}},
                  {"files": {"uploads/file.txt": "invalid-base64"}}, {"tables": {"tasks": [{"sql": "DROP TABLE tasks"}]}}]:
        assert a.client.post("/api/guest", json={**base, "state": state}).status_code == 422
    assert not (path / "escape.txt").exists()
    assert a.client.post("/api/guest", json=base, headers={"Origin": "https://evil.example"}).status_code == 403
    monkeypatch.setattr(guest, "MAX_BYTES", 20)
    assert a.client.post("/api/guest", json=base).status_code == 413

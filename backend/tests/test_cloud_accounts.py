"""Exercise real account middleware and migrated tenant databases, never local data."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import time

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import pytest

from app import accounts
from app.api.ai import get_service, tenant_services
from app.database import clear_tenant_factories
from app.main import app
from app.runtime import user_context, user_directory

ORIGIN = "https://plan.example.com"
PASSWORD = "sample-long-password-123"
INVITE = "sample-invitation-code-123"


@pytest.fixture
def cloud(monkeypatch, tmp_path):
    monkeypatch.setenv("DAYMARK_MODE", "cloud")
    monkeypatch.setenv("DAYMARK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DAYMARK_PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("DAYMARK_INVITE_CODE", INVITE)
    monkeypatch.setenv("DAYMARK_ENCRYPTION_KEY", Fernet.generate_key().decode())
    clear_tenant_factories()
    accounts.initialize()
    clients = []
    def new_client():
        client = TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})
        clients.append(client)
        return client
    yield new_client, tmp_path
    for client in clients:
        client.close()
    tenant_services.clear()
    clear_tenant_factories()


def signup(client, username):
    response = client.post("/api/auth/register", json={"username": username, "password": PASSWORD, "invite_code": INVITE})
    assert response.status_code == 201, response.text
    return response.json()


def test_auth_cookie_origin_logout_and_expiry(cloud):
    make, _ = cloud
    client = make()
    assert client.get("/api/tasks").status_code == 401
    assert client.get("/api/auth/session").json() == {"mode": "cloud", "user": None}
    bad = client.post("/api/auth/register", headers={"Origin": "https://evil.example"}, json={"username": "alice", "password": PASSWORD, "invite_code": INVITE})
    assert bad.status_code == 403
    invalid = client.post("/api/auth/register", json={"username": "alice", "password": PASSWORD, "invite_code": "wrong-invitation-code"})
    assert invalid.status_code == 403
    assert client.post("/api/auth/register", json={"username": "alice", "password": PASSWORD, "invite_code": "无效的邀请码无效的邀请码无效的邀请码"}).status_code == 403
    user = signup(client, "Alice")
    assert user["username"] == "alice"
    token = client.cookies.get(accounts.COOKIE)
    with accounts.registry() as db:
        row = db.execute("SELECT * FROM users").fetchone()
        assert PASSWORD not in row["password_hash"]
        session = db.execute("SELECT * FROM sessions").fetchone()
        assert session["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    response = client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert client.get("/api/tasks").headers["cache-control"] == "no-store"
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/tasks").status_code == 401
    assert client.post("/api/auth/login", json={"username": "alice", "password": "incorrect-password"}).status_code == 401
    client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
    with accounts.registry() as db:
        db.execute("UPDATE sessions SET expires_at=?", (int(time.time()) - 1,))
    assert client.get("/api/tasks").status_code == 401


def test_tenant_data_files_export_and_parallel_requests(cloud):
    make, path = cloud
    a, b = make(), make()
    alice, bob = signup(a, "alice"), signup(b, "bob")
    task = a.post("/api/tasks", json={"title": "Private task", "date": "2026-09-29", "start_time": "14:00", "end_time": "15:00"})
    assert task.status_code == 201, task.text
    task = task.json()
    assert b.get(f"/api/tasks/{task['id']}").status_code == 404
    assert b.put(f"/api/tasks/{task['id']}", json={"title": "Overwrite", "version": 1}).status_code == 404
    assert b.get("/api/tasks").json() == []
    assert b.get("/api/export").json()["tables"]["tasks"] == []
    convo = a.post("/api/ai/conversations", json={"title": "Private conversation"}).json()
    assert b.get(f"/api/ai/conversations/{convo['id']}").status_code == 404
    attachment = a.post(f"/api/ai/conversations/{convo['id']}/attachments?filename=private.txt", content=b"Private file").json()
    assert a.get(f"/api/ai/attachments/{attachment['id']}").content == b"Private file"
    assert b.get(f"/api/ai/attachments/{attachment['id']}").status_code == 404
    doc = a.post("/api/documents/upload?filename=note.txt&knowledge_date=2026-09-29&document_type=note", content=b"Knowledge file")
    assert doc.status_code == 201, doc.text
    assert b.get(f"/api/documents/{doc.json()['id']}/download").status_code == 404
    assert list((path / "users" / alice["id"] / "uploads").iterdir())
    assert not (path / "users" / bob["id"] / "uploads").exists()
    def check(index):
        response = (a if index % 2 == 0 else b).get("/api/tasks")
        assert response.status_code == 200
        assert len(response.json()) == (1 if index % 2 == 0 else 0)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(check, range(16)))
    assert user_context.get() is None


def test_user_keys_and_background_agent_are_bound_to_owner(cloud, monkeypatch):
    make, _ = cloud
    a, b = make(), make()
    alice, bob = signup(a, "alice"), signup(b, "bob")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "server-secret-must-not-be-shared")
    assert a.put("/api/ai/providers/deepseek/key", json={"api_key": "alice-test-secret"}).status_code == 200
    assert b.put("/api/ai/providers/deepseek/key", json={"api_key": "bob-test-secret"}).status_code == 200
    with accounts.registry() as db:
        for row in db.execute("SELECT * FROM users"):
            assert "test-secret" not in row["deepseek_key"]
            assert row["deepseek_key"].startswith("gAAAA")
    assert tenant_services[alice["id"]].config.deepseek_api_key == "alice-test-secret"
    assert tenant_services[bob["id"]].config.deepseek_api_key == "bob-test-secret"
    assert a.get("/api/ai/settings").json()["mode"] == "deepseek"
    assert a.put("/api/ai/settings", json={"mode": "local"}).status_code == 422
    convo = a.post("/api/ai/conversations", json={"title": "Agent writes"}).json()
    async def background():
        token = user_context.set(alice["id"])
        service = await get_service()
        async def child():
            await asyncio.sleep(0)
            assert user_directory().name == alice["id"]
            result = service.agent.executor.execute(convo["id"], "create_task", {"title": "Agent private task", "date": "2026-09-30", "start_time": "10:00", "end_time": "11:00"})
            assert result.success, result.message
        pending = asyncio.create_task(child())
        user_context.reset(token)
        await pending
    asyncio.run(background())
    assert b.get("/api/tasks").json() == []
    assert len(a.get("/api/tasks").json()) == 1
    # Service rebuild after a restart still reads each owner's encrypted key.
    tenant_services.clear()
    for user, expected in [(alice, "alice-test-secret"), (bob, "bob-test-secret")]:
        marker = user_context.set(user["id"])
        try:
            assert asyncio.run(get_service()).config.deepseek_api_key == expected
        finally:
            user_context.reset(marker)


def test_rate_limit_and_missing_cloud_configuration(cloud):
    make, _ = cloud
    client = make()
    for _ in range(10):
        assert client.post("/api/auth/login", json={"username": "unknown", "password": PASSWORD}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "unknown", "password": PASSWORD}).status_code == 429
    assert client.post("/api/auth/register", headers={"Origin": ""}, json={"username": "alice", "password": PASSWORD, "invite_code": INVITE}).status_code == 403


def test_cloud_startup_fails_without_secret_or_https(cloud, monkeypatch):
    monkeypatch.delenv("DAYMARK_ENCRYPTION_KEY")
    with pytest.raises(RuntimeError, match="DAYMARK_ENCRYPTION_KEY"):
        with TestClient(app):
            pass
    monkeypatch.setenv("DAYMARK_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("DAYMARK_PUBLIC_ORIGIN", "http://plan.example.com")
    with pytest.raises(RuntimeError, match="HTTPS"):
        with TestClient(app):
            pass

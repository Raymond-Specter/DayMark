from pathlib import Path

from sqlalchemy import select

from app.models import KnowledgeDocument, LearningEntry, LearningEntryDocument
from app.services import knowledge


def project(create):
    return create("projects", name="CS336", description="", start_date=None,
                  end_date=None, status="active", goal_id=None)


def test_learning_entry_crud_filters_and_task_project_inheritance(client, create):
    course = project(create)
    task = create("tasks", title="Lecture 4", description="", project_id=course["id"],
                  milestone_id=None, date="2026-09-22", start_time=None, end_time=None,
                  deadline=None, estimated_duration=75, priority=2,
                  depends_on_task_id=None, reminder=None, track_learning=True, version=None)
    payload = {
        "date": "2026-09-22", "task_id": task["id"], "title": "Lecture 4 - Attention",
        "entry_type": "study", "duration_minutes": 75, "progress": 100,
        "status": "completed", "reflection": "理解 Q/K/V", "problems": "RoPE 推导",
        "tags": ["Transformer"], "concepts": ["Query", "Key", "Value"],
    }
    created = client.post("/api/learning-entries", json=payload)
    assert created.status_code == 201, created.text
    entry = created.json()
    assert entry["project_id"] == course["id"] and entry["documents"] == []
    assert client.get(f"/api/learning-entries?project_id={course['id']}&start_date=2026-09-01").json()[0]["id"] == entry["id"]
    updated = client.patch(f"/api/learning-entries/{entry['id']}", json={
        "version": entry["version"], "duration_minutes": 90, "status": "partial",
    })
    assert updated.status_code == 200
    assert updated.json()["duration_minutes"] == 90 and updated.json()["version"] == 2
    inherited = client.patch(f"/api/learning-entries/{entry['id']}", json={
        "version": 2, "project_id": None,
    })
    assert inherited.status_code == 200
    assert inherited.json()["project_id"] == course["id"]
    assert client.patch(f"/api/learning-entries/{entry['id']}", json={
        "version": 1, "duration_minutes": 10,
    }).status_code == 409


def test_document_upload_extract_download_duplicate_and_link(client, create, tmp_path, monkeypatch, session_factory):
    monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", tmp_path / "knowledge")
    course = project(create)
    entry = client.post("/api/learning-entries", json={
        "date": "2026-09-22", "project_id": course["id"], "title": "Attention",
    }).json()
    content = b"# Attention\nQuery Key Value and scaled dot product attention."
    url = ("/api/documents/upload?filename=lecture4.md&knowledge_date=2026-09-22"
           f"&project_id={course['id']}&document_type=note&title=Lecture%204%20Notes&is_output=true")
    response = client.post(url, content=content, headers={"Content-Type": "text/markdown"})
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["processing_status"] == "ready" and document["is_output"] is True
    assert document["knowledge_date"] == "2026-09-22" and document["upload_date"] == "2026-09-21"
    detail = client.get(f"/api/documents/{document['id']}?include_text=true").json()
    assert "scaled dot product" in detail["extracted_text"]
    download = client.get(f"/api/documents/{document['id']}/download")
    assert download.content == content
    duplicate = client.post(url, content=content, headers={"Content-Type": "text/markdown"})
    assert duplicate.status_code == 409 and duplicate.json()["detail"]["code"] == "DUPLICATE_DOCUMENT"
    linked = client.post(f"/api/learning-entries/{entry['id']}/documents/{document['id']}",
                         json={"relationship": "output"})
    assert linked.status_code == 201
    assert client.get(f"/api/learning-entries/{entry['id']}").json()["documents"][0]["id"] == document["id"]
    assert client.delete(f"/api/learning-entries/{entry['id']}/documents/{document['id']}").status_code == 200
    with session_factory() as db:
        row = db.get(KnowledgeDocument, document["id"])
        assert row.sha256 and not list(db.scalars(select(LearningEntryDocument)))
        assert (tmp_path / "knowledge" / row.storage_path).is_file()
    deleted_entry = client.delete(f"/api/learning-entries/{entry['id']}")
    assert deleted_entry.status_code == 200
    assert client.get(f"/api/learning-entries/{entry['id']}").status_code == 404
    deleted_document = client.delete(f"/api/documents/{document['id']}")
    assert deleted_document.status_code == 200 and deleted_document.json()["file_retained"] is True
    assert client.get(f"/api/documents/{document['id']}").status_code == 404
    with session_factory() as db:
        row = db.get(KnowledgeDocument, document["id"])
        assert row.deleted_at and (tmp_path / "knowledge" / row.storage_path).is_file()


def test_document_metadata_patch_and_filters(client, create, tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", tmp_path / "knowledge")
    course = project(create)
    response = client.post(
        "/api/documents/upload?filename=work.py&knowledge_date=2026-09-20&document_type=code",
        content=b"print('hello')", headers={"Content-Type": "text/x-python"})
    document = response.json()
    updated = client.patch(f"/api/documents/{document['id']}", json={
        "version": document["version"], "project_id": course["id"],
        "knowledge_date": "2026-09-22", "is_output": True, "document_type": "output",
    })
    assert updated.status_code == 200
    rows = client.get(f"/api/documents?project_id={course['id']}&is_output=true&start_date=2026-09-22").json()
    assert [row["id"] for row in rows] == [document["id"]]


def test_unsupported_document_does_not_leave_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", tmp_path / "knowledge")
    response = client.post("/api/documents/upload?filename=bad.exe&knowledge_date=2026-09-22",
                           content=b"binary")
    assert response.status_code == 415
    assert not list((tmp_path / "knowledge").rglob("*.exe"))

import hashlib
import os
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from ..database import DATA
from ..models import KnowledgeDocument, LearningEntryDocument, Project, Task, now_iso
from .attachments import SUPPORTED_EXTENSIONS, extract_text, safe_filename
from .common import raw, require, today

KNOWLEDGE_DIR = DATA / "knowledge"
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_EXTRACTED_CHARS = 2_000_000


def document_dict(db, row, include_text=False):
    result = raw(row)
    if not include_text:
        result.pop("extracted_text", None)
    result["download_url"] = f"/api/documents/{row.id}/download" if row.storage_path else None
    result["learning_entry_ids"] = list(db.scalars(select(LearningEntryDocument.learning_entry_id).where(
        LearningEntryDocument.document_id == row.id)))
    return result


def entry_dict(db, row):
    result = raw(row)
    document_ids = list(db.scalars(select(LearningEntryDocument.document_id).where(
        LearningEntryDocument.learning_entry_id == row.id)))
    result["documents"] = [document_dict(db, document) for document in db.scalars(
        select(KnowledgeDocument).where(KnowledgeDocument.id.in_(document_ids), KnowledgeDocument.deleted_at.is_(None))
    )] if document_ids else []
    return result


def validate_entry_links(db, values):
    project = require(db, Project, values["project_id"]) if values.get("project_id") else None
    task = require(db, Task, values["task_id"]) if values.get("task_id") else None
    if task and project and task.project_id and task.project_id != project.id:
        raise HTTPException(422, "学习记录的项目与关联任务不一致")
    if task and not project and task.project_id:
        values["project_id"] = task.project_id
    return values


def resolved_document_path(row):
    if not row.storage_path:
        raise HTTPException(404, "该文档没有原始文件")
    root = KNOWLEDGE_DIR.resolve()
    path = (root / row.storage_path).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "文档文件不存在")
    return path


async def ingest_document(db, stream, *, filename, title, knowledge_date, project_id,
                          document_type, is_output, description, mime_type):
    filename = safe_filename(filename)
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(415, "暂不支持这种文件。第一版支持文本、Markdown、常见代码、PDF 和 DOCX。")
    if project_id:
        require(db, Project, project_id)
    temp_dir = KNOWLEDGE_DIR / ".tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{uuid4().hex}.upload"
    digest, size = hashlib.sha256(), 0
    destination = None
    document_id = None
    try:
        with temp_path.open("wb") as target:
            async for chunk in stream:
                size += len(chunk)
                if size > MAX_DOCUMENT_BYTES:
                    raise HTTPException(413, "知识文档不能超过 25 MB。")
                digest.update(chunk)
                target.write(chunk)
        if not size:
            raise HTTPException(422, "不能上传空文件。")
        sha256 = digest.hexdigest()
        duplicate = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.sha256 == sha256))
        if duplicate:
            raise HTTPException(409, detail={"code": "DUPLICATE_DOCUMENT", "message": "该文件已经存在。",
                                             "document": document_dict(db, duplicate)})
        document_id = str(uuid4())
        relative = Path(sha256[:2]) / f"{document_id}{extension}"
        destination = KNOWLEDGE_DIR / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_path, destination)
        row = KnowledgeDocument(
            id=document_id, title=title or Path(filename).stem[:200], source_type="file",
            original_filename=filename, storage_path=relative.as_posix(), file_type=extension.lstrip("."),
            mime_type=(mime_type or "application/octet-stream")[:200], file_size=size, sha256=sha256,
            project_id=project_id, knowledge_date=knowledge_date, upload_date=today(db).isoformat(),
            document_type=document_type, is_output=is_output, processing_status="parsing",
            description=description,
        )
        db.add(row)
        try:
            row.extracted_text = extract_text(filename, destination.read_bytes(), max_chars=MAX_EXTRACTED_CHARS)
            row.processing_status, row.parser_name, row.parser_version = "ready", f"builtin-{row.file_type}", "1"
            row.extracted_at = now_iso()
        except HTTPException as error:
            row.processing_status, row.extraction_error = "failed", str(error.detail)[:1000]
        db.commit()
        return row
    except Exception:
        temp_path.unlink(missing_ok=True)
        db.rollback()
        if destination and document_id and not db.get(KnowledgeDocument, document_id):
            destination.unlink(missing_ok=True)
        raise

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..learning_schemas import DocumentLinkIn, DocumentPatch, DocumentType, LearningEntryIn, LearningEntryPatch
from ..models import KnowledgeDocument, LearningEntry, LearningEntryDocument, Project, now_iso
from ..services.common import require
from ..services.knowledge import (document_dict, entry_dict, ingest_document,
                                  resolved_document_path, validate_entry_links)

router = APIRouter(prefix="/api", tags=["Learning Archive"])


def require_active(db: Session, model, key: str):
    row = require(db, model, key)
    if row.deleted_at:
        raise HTTPException(404, "记录不存在")
    return row


@router.get("/learning-entries")
def learning_entries(start_date: date | None = None, end_date: date | None = None,
                     project_id: str | None = None, entry_type: str | None = None,
                     status: str | None = None, limit: int = 200,
                     db: Session = Depends(get_db)):
    if limit < 1 or limit > 500:
        raise HTTPException(422, "limit 必须在 1–500 之间")
    query = select(LearningEntry).where(LearningEntry.deleted_at.is_(None))
    if start_date:
        query = query.where(LearningEntry.date >= start_date.isoformat())
    if end_date:
        query = query.where(LearningEntry.date <= end_date.isoformat())
    if project_id:
        query = query.where(LearningEntry.project_id == project_id)
    if entry_type:
        query = query.where(LearningEntry.entry_type == entry_type)
    if status:
        query = query.where(LearningEntry.status == status)
    rows = db.scalars(query.order_by(LearningEntry.date.desc(), LearningEntry.created_at.desc()).limit(limit))
    return [entry_dict(db, row) for row in rows]


@router.post("/learning-entries", status_code=201)
def create_learning_entry(data: LearningEntryIn, db: Session = Depends(get_db)):
    values = validate_entry_links(db, data.model_dump())
    row = LearningEntry(**values)
    db.add(row)
    db.commit()
    return entry_dict(db, row)


@router.get("/learning-entries/{key}")
def get_learning_entry(key: str, db: Session = Depends(get_db)):
    return entry_dict(db, require_active(db, LearningEntry, key))


@router.patch("/learning-entries/{key}")
def update_learning_entry(key: str, data: LearningEntryPatch, db: Session = Depends(get_db)):
    row = require_active(db, LearningEntry, key)
    if row.version != data.version:
        raise HTTPException(409, "学习记录已更新，请刷新后重试")
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    merged = {"project_id": row.project_id, "task_id": row.task_id, **changes}
    merged = validate_entry_links(db, merged)
    for field, value in changes.items():
        setattr(row, field, value)
    if merged.get("project_id") != row.project_id:
        row.project_id = merged["project_id"]
    row.version += 1
    row.updated_at = now_iso()
    db.commit()
    return entry_dict(db, row)


@router.delete("/learning-entries/{key}")
def delete_learning_entry(key: str, db: Session = Depends(get_db)):
    row = require_active(db, LearningEntry, key)
    row.deleted_at = now_iso()
    row.updated_at = row.deleted_at
    row.version += 1
    db.commit()
    return {"deleted": True, "id": key}


@router.post("/learning-entries/{key}/documents/{document_id}", status_code=201)
def link_document(key: str, document_id: str, data: DocumentLinkIn, db: Session = Depends(get_db)):
    require_active(db, LearningEntry, key)
    require_active(db, KnowledgeDocument, document_id)
    link = db.get(LearningEntryDocument, (key, document_id))
    if link:
        link.relationship = data.relationship
    else:
        link = LearningEntryDocument(learning_entry_id=key, document_id=document_id,
                                     relationship=data.relationship)
        db.add(link)
    db.commit()
    return {"linked": True, "learning_entry_id": key, "document_id": document_id,
            "relationship": link.relationship}


@router.delete("/learning-entries/{key}/documents/{document_id}")
def unlink_document(key: str, document_id: str, db: Session = Depends(get_db)):
    require_active(db, LearningEntry, key)
    link = db.get(LearningEntryDocument, (key, document_id))
    if not link:
        raise HTTPException(404, "文档关联不存在")
    db.delete(link)
    db.commit()
    return {"unlinked": True}


@router.get("/documents")
def documents(start_date: date | None = None, end_date: date | None = None,
              project_id: str | None = None, document_type: str | None = None,
              is_output: bool | None = None, limit: int = 200,
              db: Session = Depends(get_db)):
    if limit < 1 or limit > 500:
        raise HTTPException(422, "limit 必须在 1–500 之间")
    query = select(KnowledgeDocument).where(KnowledgeDocument.deleted_at.is_(None))
    if start_date:
        query = query.where(KnowledgeDocument.knowledge_date >= start_date.isoformat())
    if end_date:
        query = query.where(KnowledgeDocument.knowledge_date <= end_date.isoformat())
    if project_id:
        query = query.where(KnowledgeDocument.project_id == project_id)
    if document_type:
        query = query.where(KnowledgeDocument.document_type == document_type)
    if is_output is not None:
        query = query.where(KnowledgeDocument.is_output == is_output)
    rows = db.scalars(query.order_by(KnowledgeDocument.knowledge_date.desc(),
                                     KnowledgeDocument.created_at.desc()).limit(limit))
    return [document_dict(db, row) for row in rows]


@router.post("/documents/upload", status_code=201)
async def upload_document(request: Request, filename: str, knowledge_date: date,
                          project_id: str | None = None, document_type: DocumentType = "other",
                          title: str = "", is_output: bool = False, description: str = "",
                          db: Session = Depends(get_db)):
    row = await ingest_document(
        db, request.stream(), filename=filename, title=title[:200],
        knowledge_date=knowledge_date.isoformat(), project_id=project_id,
        document_type=document_type, is_output=is_output, description=description[:20000],
        mime_type=request.headers.get("content-type"),
    )
    return document_dict(db, row)


@router.get("/documents/{key}")
def get_document(key: str, include_text: bool = False, db: Session = Depends(get_db)):
    return document_dict(db, require_active(db, KnowledgeDocument, key), include_text=include_text)


@router.patch("/documents/{key}")
def update_document(key: str, data: DocumentPatch, db: Session = Depends(get_db)):
    row = require_active(db, KnowledgeDocument, key)
    if row.version != data.version:
        raise HTTPException(409, "文档已更新，请刷新后重试")
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    if changes.get("project_id"):
        require(db, Project, changes["project_id"])
    for field, value in changes.items():
        setattr(row, field, value)
    row.version += 1
    row.updated_at = now_iso()
    db.commit()
    return document_dict(db, row)


@router.delete("/documents/{key}")
def delete_document(key: str, db: Session = Depends(get_db)):
    row = require_active(db, KnowledgeDocument, key)
    row.deleted_at = now_iso()
    row.updated_at = row.deleted_at
    row.version += 1
    db.commit()
    return {"deleted": True, "id": key, "file_retained": bool(row.storage_path)}


@router.get("/documents/{key}/download")
def download_document(key: str, db: Session = Depends(get_db)):
    row = require_active(db, KnowledgeDocument, key)
    return FileResponse(resolved_document_path(row), media_type=row.mime_type,
                        filename=row.original_filename or row.title)

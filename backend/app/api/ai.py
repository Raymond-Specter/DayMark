from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai_schemas import ChatIn, ConfirmationIn, ConversationIn, DeepSeekKeyIn, ModelSettings
from ..database import SessionLocal, get_db
from ..models import AISettings, AgentActionLog, ChatAttachment, Conversation
from ..agent.agent_service import AgentService
from ..agent.registry import build_registry
from ..agent.tool_executor import ToolExecutor
from ..services.common import raw, require
from ..services.conversation import ConversationService, history, read_settings
from ..services.attachments import (MAX_FILE_BYTES, attachment_dict, attachment_path,
                                    delete_upload, extract_text, safe_filename, save_upload)
from ..services.llm.base import LLMError
from ..services.llm.config import LLMConfig, save_env_secret
from ..services.llm.ollama_provider import OllamaProvider
from ..services.llm.deepseek_provider import DeepSeekProvider
from ..services.llm.router import ProviderRouter

router = APIRouter(prefix="/api/ai", tags=["AI Assistant"])


@lru_cache
def service_instance():
    # Construct lazily: an invalid AI configuration must not break Calendar.
    try:
        config = LLMConfig.from_env()
    except ValueError as error:
        raise HTTPException(503, f"AI 配置无效：{error}")
    router_service = ProviderRouter(
        DeepSeekProvider(config.deepseek_base_url, config.deepseek_api_key, config.deepseek_model),
        OllamaProvider(config.base_url), config,
    )
    registry = build_registry()
    executor = ToolExecutor(registry, SessionLocal)
    agent = AgentService(router_service, registry, executor, SessionLocal)
    return ConversationService(router_service, config, agent)


async def get_service():
    # Resolve on the event loop, so simultaneous first requests share one owner.
    return service_instance()


@router.get("/health")
async def health(db: Session = Depends(get_db), service=Depends(get_service)):
    selected = read_settings(db, service.config)
    if hasattr(service.llm, "status"):
        providers = await service.llm.status(selected.model)
        local = providers["local"]
        return {"providers": providers, "selected_mode": selected.mode,
                "ollama_available": local["online"], "model_available": local.get("model_available", False),
                "model": selected.model, "error": local.get("error"), "busy": service.active is not None,
                "agent_enabled": service.agent is not None, "settings": selected.model_dump()}
    return {**await service.llm.health(selected.model), "busy": service.active is not None,
            "agent_enabled": service.agent is not None, "settings": selected.model_dump()}


@router.get("/providers/status")
async def provider_status(db: Session = Depends(get_db), service=Depends(get_service)):
    selected = read_settings(db, service.config)
    if not hasattr(service.llm, "status"):
        return {"selected_mode": selected.mode, "providers": {}}
    return {"selected_mode": selected.mode, "providers": await service.llm.status(selected.model)}


@router.put("/providers/deepseek/key")
async def save_deepseek_key(data: DeepSeekKeyIn, service=Depends(get_service)):
    if service.active:
        raise HTTPException(409, "请先停止生成再修改 API Key。")
    key = data.api_key.get_secret_value().strip()
    try:
        save_env_secret("DEEPSEEK_API_KEY", key)
    except (OSError, ValueError) as error:
        raise HTTPException(500 if isinstance(error, OSError) else 422,
                            "API Key 无法保存到项目 .env。" if isinstance(error, OSError) else str(error))
    service.config.deepseek_api_key = key
    service.llm.config.deepseek_api_key = key
    service.llm.deepseek.provider.api_key = key
    return {"configured": True, "model": service.config.deepseek_model}


@router.get("/models")
async def models(service=Depends(get_service)):
    try:
        llm = service.llm.local if hasattr(service.llm, "local") else service.llm
        return await llm.list_models()
    except LLMError as error:
        raise HTTPException(error.status, error.message)


@router.get("/settings")
def settings(db: Session = Depends(get_db), service=Depends(get_service)):
    return read_settings(db, service.config)


@router.put("/settings")
async def save_settings(data: ModelSettings, db: Session = Depends(get_db), service=Depends(get_service)):
    if service.active:
        raise HTTPException(409, "请先停止生成再修改模型设置。")
    if data.model.endswith(":cloud") or "cloud" in data.model.split(":")[-1]:
        raise HTTPException(422, "Local Model 只能选择本地 Ollama 模型。")
    row = db.get(AISettings, 1)
    if row is None:
        row = AISettings(id=1)
        db.add(row)
    row.mode, row.model, row.num_ctx, row.temperature, row.think = data.mode, data.model, data.num_ctx, str(data.temperature), data.think
    db.commit()
    return data


@router.get("/conversations")
def conversations(db: Session = Depends(get_db)):
    return [raw(row) for row in db.scalars(select(Conversation).order_by(Conversation.updated_at.desc()).limit(200))]


@router.post("/conversations", status_code=201)
def create_conversation(data: ConversationIn, db: Session = Depends(get_db)):
    row = Conversation(title=data.title)
    db.add(row)
    db.commit()
    return raw(row)


def _message_dict(row, attachment_map):
    return {**raw(row), "attachments": [attachment_dict(item) for item in attachment_map.get(row.id, [])]}


@router.get("/conversations/{key}")
def conversation(key: str, db: Session = Depends(get_db)):
    conversation_row = require(db, Conversation, key)
    attachments = list(db.scalars(select(ChatAttachment).where(ChatAttachment.conversation_id == key)))
    attachment_map = {}
    for attachment in attachments:
        if attachment.message_id:
            attachment_map.setdefault(attachment.message_id, []).append(attachment)
    return {**raw(conversation_row), "messages": [_message_dict(row, attachment_map) for row in history(db, key)]}


@router.post("/conversations/{key}/attachments", status_code=201)
async def upload_attachment(key: str, request: Request, filename: str, db: Session = Depends(get_db)):
    require(db, Conversation, key)
    filename = safe_filename(filename)
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(413, "文件不能超过 10 MB。")
    if not content:
        raise HTTPException(422, "不能上传空文件。")
    raw_content = bytes(content)
    text = extract_text(filename, raw_content)
    storage_name = save_upload(filename, raw_content)
    row = ChatAttachment(
        conversation_id=key, filename=filename,
        media_type=(request.headers.get("content-type") or "application/octet-stream")[:200],
        size_bytes=len(raw_content), storage_name=storage_name, extracted_text=text,
    )
    try:
        db.add(row)
        db.commit()
    except Exception:
        delete_upload(storage_name)
        raise
    return attachment_dict(row)


@router.get("/attachments/{attachment_id}")
def download_attachment(attachment_id: str, db: Session = Depends(get_db)):
    row = require(db, ChatAttachment, attachment_id)
    path = attachment_path(row.storage_name)
    if not path.is_file():
        raise HTTPException(404, "附件文件不存在。")
    return FileResponse(path, media_type=row.media_type, filename=row.filename)


@router.delete("/attachments/{attachment_id}")
def remove_attachment(attachment_id: str, db: Session = Depends(get_db)):
    row = require(db, ChatAttachment, attachment_id)
    if row.message_id:
        raise HTTPException(409, "已经发送的附件不能从消息中单独删除。")
    storage_name = row.storage_name
    db.delete(row)
    db.commit()
    delete_upload(storage_name)
    return {"deleted": True}


@router.delete("/conversations/{key}")
async def delete_conversation(key: str, db: Session = Depends(get_db), service=Depends(get_service)):
    if service.active and service.active.conversation_id == key:
        raise HTTPException(409, "请先停止生成再删除会话。")
    row = require(db, Conversation, key)
    uploads = [attachment.storage_name for attachment in db.scalars(
        select(ChatAttachment).where(ChatAttachment.conversation_id == key))]
    db.delete(row)
    db.commit()
    for storage_name in uploads:
        delete_upload(storage_name)
    return {"deleted": True}


@router.post("/conversations/{key}/stop")
async def stop(key: str, db: Session = Depends(get_db), service=Depends(get_service)):
    require(db, Conversation, key)
    return {"stopped": await service.stop(key)}


@router.post("/chat")
async def chat(data: ChatIn, db: Session = Depends(get_db), service=Depends(get_service)):
    run = service.start(db, data)
    if data.stream:
        return StreamingResponse(service.events(run), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})
    await run.task
    return run.result


@router.post("/confirm/{action_id}")
async def confirm_action(action_id: str, data: ConfirmationIn, db: Session = Depends(get_db), service=Depends(get_service)):
    require(db, Conversation, data.conversation_id)
    result = service.agent.executor.confirm(data.conversation_id, action_id, data.approve)
    return result.model_dump()


@router.get("/conversations/{key}/actions")
def action_log(key: str, db: Session = Depends(get_db)):
    require(db, Conversation, key)
    return [raw(row) for row in db.scalars(select(AgentActionLog).where(
        AgentActionLog.conversation_id == key).order_by(AgentActionLog.created_at.desc()).limit(100))]

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai_schemas import ChatIn, ConfirmationIn, ConversationIn, ModelSettings
from ..database import SessionLocal, get_db
from ..models import AISettings, AgentActionLog, Conversation
from ..agent.agent_service import AgentService
from ..agent.registry import build_registry
from ..agent.tool_executor import ToolExecutor
from ..services.common import raw, require
from ..services.conversation import ConversationService, history, read_settings
from ..services.llm.base import LLMError
from ..services.llm.config import LLMConfig
from ..services.llm.ollama_provider import OllamaProvider
from ..services.llm.service import LLMService

router = APIRouter(prefix="/api/ai", tags=["AI Assistant"])


@lru_cache
def service_instance():
    # Construct lazily: an invalid AI configuration must not break Calendar.
    try:
        config = LLMConfig.from_env()
    except ValueError as error:
        raise HTTPException(503, f"AI 配置无效：{error}")
    llm = LLMService(OllamaProvider(config.base_url))
    registry = build_registry()
    executor = ToolExecutor(registry, SessionLocal)
    agent = AgentService(llm, registry, executor, SessionLocal)
    return ConversationService(llm, config, agent)


async def get_service():
    # Resolve on the event loop, so simultaneous first requests share one owner.
    return service_instance()


@router.get("/health")
async def health(db: Session = Depends(get_db), service=Depends(get_service)):
    selected = read_settings(db, service.config)
    return {**await service.llm.health(selected.model), "busy": service.active is not None,
            "agent_enabled": service.agent is not None, "settings": selected.model_dump()}


@router.get("/models")
async def models(service=Depends(get_service)):
    try:
        return await service.llm.list_models()
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
        raise HTTPException(422, "此版本只使用本地模型。")
    row = db.get(AISettings, 1)
    if row is None:
        row = AISettings(id=1)
        db.add(row)
    row.model, row.num_ctx, row.temperature, row.think = data.model, data.num_ctx, str(data.temperature), data.think
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


@router.get("/conversations/{key}")
def conversation(key: str, db: Session = Depends(get_db)):
    return {**raw(require(db, Conversation, key)), "messages": [raw(row) for row in history(db, key)]}


@router.delete("/conversations/{key}")
async def delete_conversation(key: str, db: Session = Depends(get_db), service=Depends(get_service)):
    if service.active and service.active.conversation_id == key:
        raise HTTPException(409, "请先停止生成再删除会话。")
    row = require(db, Conversation, key)
    db.delete(row)
    db.commit()
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

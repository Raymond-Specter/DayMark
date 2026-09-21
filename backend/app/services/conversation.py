import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ..ai_schemas import ModelSettings
from ..models import AISettings, ChatAttachment, ChatMessage, Conversation, now_iso
from .common import require
from .llm.base import GenerationOptions, LLMError, Message
from .llm.config import LLMConfig
from .llm.service import LLMService

logger = logging.getLogger(__name__)
SYSTEM_PROMPT = (Path(__file__).resolve().parents[1] / "prompts/planner_system_prompt.txt").read_text(encoding="utf-8")


def read_settings(db, config: LLMConfig):
    row = db.get(AISettings, 1)
    return ModelSettings(model=row.model, num_ctx=row.num_ctx, temperature=float(row.temperature), think=row.think) if row else ModelSettings(
        model=config.model, num_ctx=config.num_ctx, temperature=config.temperature, think=config.think)


def history(db, key):
    require(db, Conversation, key)
    return list(db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == key).order_by(ChatMessage.position)))


def _with_attachments(content, attachments):
    if not attachments:
        return content
    sections = [content]
    for attachment in attachments:
        sections.append(f"[附件：{attachment.filename}]\n{attachment.extracted_text}")
    return "\n\n".join(sections)


def build_context(rows, message, options, system_prompt=SYSTEM_PROMPT, attachment_map=None, current_attachments=None):
    # A conservative UTF-8 budget preserves full recent exchanges and always the
    # current question/system prompt. It is a bound, not a model tokenizer.
    budget = (options.num_ctx - 1024) * 2
    attachment_map = attachment_map or {}
    current = [Message("system", system_prompt), Message("user", _with_attachments(message, current_attachments or []))]
    used = sum(len(m.content.encode("utf-8")) + 64 for m in current)
    if used > budget:
        raise HTTPException(422, "消息超过当前上下文预算，请缩短消息或提高上下文长度。")
    pairs = []
    for index in range(1, len(rows)):
        before, after = rows[index - 1], rows[index]
        if before.role == "user" and after.role == "assistant" and after.status == "completed":
            pairs.append([Message("user", _with_attachments(before.content, attachment_map.get(before.id, []))),
                          Message("assistant", after.content)])
    chosen = []
    for pair in reversed(pairs):
        size = sum(len(m.content.encode("utf-8")) + 64 for m in pair)
        if used + size > budget:
            break
        chosen = pair + chosen
        used += size
    return [current[0], *chosen, current[1]], len(chosen) < len(pairs) * 2


@dataclass
class Run:
    conversation_id: str
    message_id: str
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: asyncio.Task | None = None
    result: dict | None = None
    stopping: bool = False


class ConversationService:
    """Persisted streaming chat with an optional service-backed Agent."""
    def __init__(self, llm: LLMService, config: LLMConfig, agent=None):
        self.llm, self.config, self.agent = llm, config, agent
        self.active: Run | None = None

    def start(self, db, payload):
        if self.active is not None:
            raise HTTPException(409, "已有一个回答正在生成，请先停止或等待完成。")
        conversation = require(db, Conversation, payload.conversation_id)
        settings = read_settings(db, self.config)
        options = GenerationOptions(**settings.model_dump(), timeout=self.config.timeout)
        rows = history(db, conversation.id)
        attachments = list(db.scalars(select(ChatAttachment).where(ChatAttachment.conversation_id == conversation.id)))
        attachment_map = {}
        for attachment in attachments:
            if attachment.message_id:
                attachment_map.setdefault(attachment.message_id, []).append(attachment)
        selected_attachments = [attachment for attachment in attachments if attachment.id in payload.attachment_ids]
        if len(selected_attachments) != len(set(payload.attachment_ids)) or any(row.message_id for row in selected_attachments):
            raise HTTPException(422, "附件不存在、已发送或不属于当前对话，请重新上传。")
        prompt = self.agent.system_prompt_for_conversation(db, conversation.id) if self.agent else SYSTEM_PROMPT
        messages, truncated = build_context(rows, payload.message, options, prompt, attachment_map, selected_attachments)
        position = rows[-1].position + 1 if rows else 1
        user = ChatMessage(conversation_id=conversation.id, role="user", content=payload.message, position=position)
        assistant = ChatMessage(conversation_id=conversation.id, role="assistant", content="", status="generating", model=options.model, position=position + 1)
        db.add(user)
        db.flush()
        for attachment in selected_attachments:
            attachment.message_id = user.id
        db.add(assistant)
        if conversation.title == "新对话":
            conversation.title = payload.message[:60]
        conversation.updated_at = now_iso()
        db.commit()
        run = Run(conversation.id, assistant.id)
        self.active = run
        factory = sessionmaker(db.get_bind(), expire_on_commit=False)
        run.queue.put_nowait({"event": "start", "conversation_id": conversation.id, "message_id": assistant.id, "context_trimmed": truncated})
        run.task = asyncio.create_task(self._generate(run, factory, messages, options))
        return run

    async def _generate(self, run, factory, messages, options):
        content, status, error, metrics = "", "completed", None, {}
        affected_entities, confirmation = [], None
        started, saved_at = monotonic(), monotonic()
        try:
            async def emit(event):
                nonlocal content, saved_at
                if event["event"] == "delta":
                    content += event.get("content", "")
                elif event["event"] == "reset":
                    content = ""
                run.queue.put_nowait(event)
                if monotonic() - saved_at >= 0.5:
                    self._save(factory, run, content, "generating", None, started)
                    saved_at = monotonic()

            async def consume():
                nonlocal content, metrics, affected_entities, confirmation
                if self.agent:
                    outcome = await self.agent.run(run.conversation_id, messages, options, emit)
                    content, metrics = outcome.content, outcome.metrics
                    affected_entities, confirmation = outcome.affected_entities, outcome.confirmation
                    return
                stream = self.llm.stream_chat(messages, options)
                async for chunk in stream:
                    if chunk.tool_calls:
                        raise LLMError("tools_disabled", "当前尚未启用工具调用，未执行任何规划操作。", 409)
                    if chunk.content:
                        await emit({"event": "delta", "content": chunk.content})
                    metrics.update(chunk.metrics)
            await asyncio.wait_for(consume(), timeout=options.timeout)
            if not content.strip():
                raise LLMError("empty_answer", "模型未返回最终回答，请关闭 Thinking 或重试。", 502)
        except asyncio.CancelledError:
            status = "stopped"
        except (asyncio.TimeoutError, LLMError) as exc:
            status = "error"
            error = exc.message if isinstance(exc, LLMError) else "生成超过总时限，已保留部分回答，请重试。"
        except Exception:
            logger.exception("AI generation failed")
            status, error = "error", "生成或保存失败，请检查后端日志后重试。"
        finally:
            try:
                self._save(factory, run, content, status, error, started)
            except Exception:
                logger.exception("Could not persist final chat message")
                status, error = "error", "数据库保存失败，当前回答可能未完整保存，请检查磁盘和后端日志。"
            run.result = {"event": "error" if error else "done", "message_id": run.message_id, "conversation_id": run.conversation_id,
                          "content": content, "status": status, "error": error, "duration_ms": round((monotonic() - started) * 1000),
                          "metrics": metrics, "affected_entities": affected_entities, "confirmation": confirmation}
            run.queue.put_nowait(run.result)
            if self.active is run:
                self.active = None

    def _save(self, factory, run, content, status, error, started):
        with factory() as db:
            row = db.get(ChatMessage, run.message_id)
            if row:
                row.content, row.status, row.error = content, status, error
                row.duration_ms = round((monotonic() - started) * 1000)
                conversation = db.get(Conversation, run.conversation_id)
                if conversation:
                    conversation.updated_at = now_iso()
                db.commit()

    async def stop(self, key):
        run = self.active
        if run and run.conversation_id == key and run.task:
            if not run.stopping:
                run.stopping = True
                await asyncio.sleep(0)  # Let a just-created task enter its cleanup scope.
                run.task.cancel()
            await asyncio.shield(run.task)
            return True
        return False

    async def events(self, run):
        try:
            terminal = False
            while not terminal:
                try:
                    event = await asyncio.wait_for(run.queue.get(), 10)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                terminal = event["event"] in {"done", "error"}
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            if self.active is run:
                # Explicit stop is the primary UI path; disconnect also cancels.
                await asyncio.shield(self.stop(run.conversation_id))

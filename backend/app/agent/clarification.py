"""Persist user questions separately from business data; only user turns resolve them."""
from fastapi import HTTPException
from sqlalchemy import select

from ..models import PendingAgentAction, now_iso


def pending_question(db, conversation_id):
    return db.scalar(select(PendingAgentAction).where(
        PendingAgentAction.conversation_id == conversation_id,
        PendingAgentAction.tool_name == "ask_user",
        PendingAgentAction.status == "pending",
    ).order_by(PendingAgentAction.created_at.desc()))


def question_dict(row):
    if not row:
        return None
    return {"id": row.id, **row.tool_arguments}


def answer_question(db, conversation_id, message, clarification_id=None, answers=None):
    row = pending_question(db, conversation_id)
    if clarification_id:
        if not row or row.id != clarification_id:
            raise HTTPException(409, "问题已回答、已失效或不属于当前会话，请刷新。")
        questions = row.tool_arguments["questions"]
        if not answers or set(answers) != {question["id"] for question in questions}:
            raise HTTPException(422, "请回答全部问题，也可以输入自己的答案。")
        lines = [f"用户补充信息（原请求：{row.tool_arguments['context']}）："]
        for question in questions:
            value = answers[question["id"]].strip()
            if not value or len(value) > 2000:
                raise HTTPException(422, "每个答案需为1至2000个字符。")
            lines.append(f"{question['question']}：{value}")
        message = "\n".join(lines)
    elif answers:
        raise HTTPException(422, "回答必须关联当前问题。")
    if row:
        row.status, row.resolved_at = "answered", now_iso()
        # This record also preserves the original constraints if chat is trimmed.
        row.tool_arguments = {**row.tool_arguments, "answer": message}
    return message

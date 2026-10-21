import asyncio
from collections import defaultdict

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.agent.agent_service import AgentService
from app.agent.clarification import answer_question, pending_question
from app.agent.planner_service import AgentPlannerService
from app.agent.registry import build_registry
from app.agent.tool_executor import ToolExecutor
from app.models import CalendarEvent, Conversation, PendingAgentAction, Routine, Task
from app.services.common import raw
from app.services.llm.base import ChatChunk, GenerationOptions, Message
from app.services.llm.service import LLMService


@pytest.fixture
def planning(session_factory):
    with session_factory() as db:
        row = Conversation()
        db.add(row)
        db.commit()
    return row.id, ToolExecutor(build_registry(), session_factory)


def plan(**changes):
    return {
        "title": "学习托福", "daily_minutes": 300,
        "start_date": "2026-09-22", "end_date": "2026-09-24",
        "windows": [{"start_time": "09:00", "end_time": "12:00"},
                    {"start_time": "14:00", "end_time": "20:00"}],
        "allow_split": True, "min_session_minutes": 60, **changes,
    }


def test_preview_then_confirm_daily_total_without_changing_existing(planning, session_factory):
    key, tools = planning
    existing = tools.execute(key, "create_task", {
        "title": "原有课程", "date": "2026-09-22", "start_time": "09:00", "end_time": "11:00"})
    event = tools.execute(key, "create_event", {
        "title": "独立会议", "start": "2026-09-23T14:00", "end": "2026-09-23T17:00"})
    with session_factory() as db:
        original_task = raw(db.get(Task, existing.data["id"]))
        original_event = raw(db.get(CalendarEvent, event.data["id"]))
    result = tools.execute(key, "plan_daily_tasks", plan())
    assert result.error_code == "CONFIRMATION_REQUIRED"
    assert all(day["scheduled_minutes"] == 300 for day in result.data["days"])
    assert result.data["days"][0]["slots"] != result.data["days"][1]["slots"]
    with session_factory() as db:
        assert len(list(db.scalars(select(Task)))) == 1
    confirmed = tools.confirm(key, result.confirmation["action_id"], True)
    assert confirmed.success
    totals = defaultdict(int)
    with session_factory() as db:
        assert raw(db.get(Task, existing.data["id"])) == original_task
        assert raw(db.get(CalendarEvent, event.data["id"])) == original_event
        for task in db.scalars(select(Task).where(Task.title == "学习托福")):
            totals[task.date] += task.estimated_duration
            assert not AgentPlannerService(db).conflicts(task.date, task.start_time, task.end_time, task.id)
        assert set(totals.values()) == {300} and len(totals) == 3
    undo = tools.execute(key, "undo_last_action", {})
    assert undo.success
    with session_factory() as db:
        assert raw(db.get(Task, existing.data["id"])) == original_task
        assert not list(db.scalars(select(Task).where(Task.title == "学习托福", Task.deleted_at.is_(None))))


def test_missing_preferences_asks_and_blocks_writes_until_user_answers(planning, session_factory):
    key, tools = planning
    result = tools.execute(key, "plan_daily_tasks", {"title": "托福", "daily_minutes": 300})
    assert result.clarification
    assert len(result.clarification["questions"]) == 4
    blocked = tools.execute(key, "create_task", {"title": "不应创建", "date": "2026-09-22"})
    assert blocked.error_code == "INFORMATION_REQUIRED"
    with pytest.raises(HTTPException):
        tools.confirm(key, result.clarification["id"], True)
    with session_factory() as db:
        assert pending_question(db, key) is not None
        answers = {item["id"]: "用户自己的答案" for item in result.clarification["questions"]}
        message = answer_question(db, key, "补充信息", result.clarification["id"], answers)
        assert "用户自己的答案" in message and "300" in message
        db.commit()
        assert pending_question(db, key) is None
        assert not list(db.scalars(select(Task)))


def test_shortage_asks_instead_of_partial_writes(planning, session_factory):
    key, tools = planning
    args = plan(windows=[{"start_time": "09:00", "end_time": "12:00"}])
    result = tools.execute(key, "plan_daily_tasks", args)
    assert result.clarification and result.confirmation is None
    assert all(day["shortfall_minutes"] == 120 for day in result.data["days"])
    with session_factory() as db:
        assert not list(db.scalars(select(Task)))


def test_explicitly_selected_existing_tasks_count_towards_daily_target(planning, session_factory):
    key, tools = planning
    existing = tools.execute(key, "create_task", {
        "title": "早间托福", "date": "2026-09-22", "start_time": "07:00", "end_time": "08:00"})
    result = tools.execute(key, "plan_daily_tasks", plan(counted_task_ids=[existing.data["id"], existing.data["id"]]))
    first, second = result.data["days"][:2]
    assert (first["existing_minutes"], first["scheduled_minutes"]) == (60, 240)
    assert (second["existing_minutes"], second["scheduled_minutes"]) == (0, 300)
    assert tools.confirm(key, result.confirmation["action_id"], True).success
    with session_factory() as db:
        assert db.get(Task, existing.data["id"]).version == 1


def test_unselected_similar_task_not_automatically_counted(planning):
    key, tools = planning
    tools.execute(key, "create_task", {
        "title": "学习托福", "date": "2026-09-22", "start_time": "07:00", "end_time": "08:00"})
    result = tools.execute(key, "plan_daily_tasks", plan())
    assert result.data["days"][0]["existing_minutes"] == 0
    assert result.data["days"][0]["scheduled_minutes"] == 300


def test_fixed_future_routine_reserved_without_materializing(planning, session_factory):
    key, tools = planning
    with session_factory() as db:
        row = Routine(name="未来课程", frequency="daily", start_date="2026-10-30",
                      preferred_time="09:00", estimated_duration=180)
        db.add(row)
        db.commit()
        before = raw(row)
    result = tools.execute(key, "plan_daily_tasks", plan(start_date="2026-10-30", end_date="2026-10-30"))
    assert result.confirmation
    assert result.data["days"][0]["slots"][0]["start_time"] == "14:00"
    with session_factory() as db:
        assert not list(db.scalars(select(Task)))
        assert raw(db.get(Routine, row.id)) == before


def test_calendar_change_after_preview_rejects_whole_plan(planning, session_factory):
    key, tools = planning
    preview = tools.execute(key, "plan_daily_tasks", plan())
    tools.execute(key, "create_event", {"title": "新增会议", "start": "2026-09-22T09:00", "end": "2026-09-22T10:00"})
    result = tools.confirm(key, preview.confirmation["action_id"], True)
    assert result.error_code == "PLAN_CHANGED"
    with session_factory() as db:
        assert not list(db.scalars(select(Task)))


def test_confirmation_cannot_cross_conversations_or_be_replayed(planning, session_factory):
    key, tools = planning
    result = tools.execute(key, "plan_daily_tasks", plan())
    with session_factory() as db:
        other = Conversation()
        db.add(other)
        db.commit()
    with pytest.raises(HTTPException):
        tools.confirm(other.id, result.confirmation["action_id"], True)
    assert tools.confirm(key, result.confirmation["action_id"], True).success
    with pytest.raises(HTTPException):
        tools.confirm(key, result.confirmation["action_id"], True)
    with session_factory() as db:
        assert len(list(db.scalars(select(Task)))) == result.data["task_count"]


def test_failure_rolls_back_all_new_tasks(planning, session_factory, monkeypatch):
    key, tools = planning
    preview = tools.execute(key, "plan_daily_tasks", plan())
    original = AgentPlannerService.create
    calls = 0

    def fail_second(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("模拟写入失败")
        return original(self, *args, **kwargs)
    monkeypatch.setattr(AgentPlannerService, "create", fail_second)
    result = tools.confirm(key, preview.confirmation["action_id"], True)
    assert not result.success
    with session_factory() as db:
        assert not list(db.scalars(select(Task)))
        assert not list(db.scalars(select(CalendarEvent)))


def test_all_day_and_cross_midnight_events_block_time(planning):
    key, tools = planning
    tools.execute(key, "create_event", {"title": "跨天", "start": "2026-09-21T22:00", "end": "2026-09-22T10:00"})
    preview = tools.execute(key, "plan_daily_tasks", plan(end_date="2026-09-22"))
    assert preview.data["days"][0]["slots"][0]["start_time"] == "10:00"
    event = tools.execute(key, "create_event", {"title": "全天", "start": "2026-09-23", "end": "2026-09-24", "all_day": True})
    assert event.success
    shortage = tools.execute(key, "plan_daily_tasks", plan())
    assert shortage.clarification
    assert shortage.data["days"][1]["shortfall_minutes"] == 300


def test_question_persistence_and_invalid_answer_are_isolated(planning, session_factory, client):
    key, tools = planning
    result = tools.execute(key, "ask_user", {"context": "每天学习托福5小时", "questions": [
        {"id": "split", "question": "可以分段吗？", "options": ["可以", "不可以"]}]})
    detail = client.get(f"/api/ai/conversations/{key}").json()
    assert detail["clarification"] == result.clarification
    with session_factory() as db:
        with pytest.raises(HTTPException):
            answer_question(db, key, "补充", result.clarification["id"], {"wrong": "可以"})
        db.rollback()
        assert pending_question(db, key) is not None
        with pytest.raises(HTTPException):
            answer_question(db, "other", "补充", result.clarification["id"], {"split": "可以"})
        db.rollback()
        assert db.get(PendingAgentAction, result.clarification["id"]).status == "pending"


def test_planning_preview_restored_after_reload(planning, client):
    key, tools = planning
    result = tools.execute(key, "plan_daily_tasks", plan())
    detail = client.get(f"/api/ai/conversations/{key}").json()
    assert detail["confirmation"] == result.confirmation
    assert "_preview" not in detail["confirmation"]["arguments"]


def test_question_in_parallel_batch_prevents_any_write(planning, session_factory):
    key, tools = planning

    class Provider:
        async def stream_chat(self, messages, options, schemas=None):
            yield ChatChunk(tool_calls=[
                {"id": "write", "function": {"name": "create_task", "arguments": {"title": "不应创建", "date": "2026-09-22"}}},
                {"id": "ask", "function": {"name": "ask_user", "arguments": {
                    "context": "每天学5小时托福", "questions": [
                        {"id": "dates", "question": "规划多少天？", "options": ["7天", "30天"]}]}}},
            ], done=True)

    async def run():
        events = []
        async def emit(event):
            events.append(event)
        agent = AgentService(LLMService(Provider()), build_registry(), tools, session_factory)
        outcome = await agent.run(key, [Message("system", "test"), Message("user", "未来每天学5h托福")],
                                  GenerationOptions(), emit)
        assert outcome.clarification and not outcome.affected_entities
        assert [event["tool"] for event in events if event["event"] == "tool_result"] == ["ask_user"]
    asyncio.run(run())
    with session_factory() as db:
        assert not list(db.scalars(select(Task)))


@pytest.mark.parametrize("changes", [
    {"end_date": "2026-12-01"}, {"start_date": "2026-09-01"},
    {"windows": [{"start_time": "09:00", "end_time": "12:00"}, {"start_time": "11:00", "end_time": "14:00"}]},
])
def test_invalid_date_range_and_overlapping_windows_do_not_write(planning, session_factory, changes):
    key, tools = planning
    result = tools.execute(key, "plan_daily_tasks", plan(**changes))
    assert not result.success and not result.confirmation
    with session_factory() as db:
        assert not list(db.scalars(select(Task)))

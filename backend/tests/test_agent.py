import asyncio

from sqlalchemy import select

from app.agent.agent_service import AgentService
from app.agent.registry import build_registry
from app.agent.tool_executor import ToolExecutor
from app.models import AgentActionLog, CalendarEvent, Conversation, Routine, Task
from app.services.llm.base import ChatChunk, GenerationOptions, Message
from app.services.llm.service import LLMService


class ScriptedProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def stream_chat(self, messages, options, tools=None):
        self.requests.append((messages, tools))
        yield self.responses.pop(0)


def executor(session_factory):
    registry = build_registry()
    return registry, ToolExecutor(registry, session_factory)


def test_minimum_agent_loop_creates_real_task_and_reads_it(session_factory):
    async def run():
        with session_factory() as db:
            conversation = Conversation(); db.add(conversation); db.commit()
        provider = ScriptedProvider([
            ChatChunk(tool_calls=[{"id": "1", "function": {"name": "create_task", "arguments": {
                "title": "托福刷题", "date": "2026-09-22", "start_time": "15:00", "duration_minutes": 90,
            }}}], done=True),
            ChatChunk(content="已安排明天下午 3 点的托福刷题。", done=True),
        ])
        registry, tool_executor = executor(session_factory)
        agent = AgentService(LLMService(provider), registry, tool_executor, session_factory)
        events = []
        outcome = await agent.run(conversation.id, [Message("system", "test"), Message("user", "安排托福")],
                                  GenerationOptions(), lambda event: events.append(event) or asyncio.sleep(0))
        assert outcome.affected_entities[0]["type"] == "task"
        assert any(event["event"] == "tool_status" for event in events)
        with session_factory() as db:
            task = db.scalar(select(Task).where(Task.title == "托福刷题"))
            assert (task.date, task.start_time, task.end_time) == ("2026-09-22", "15:00", "16:30")
            event = db.scalar(select(CalendarEvent).where(CalendarEvent.task_id == task.id))
            assert event.start == "2026-09-22T15:00:00"
            assert db.scalar(select(AgentActionLog)).status == "success"
        assert provider.requests[0][1] and provider.requests[1][0][-1].role == "tool"
    asyncio.run(run())


def test_agent_retries_instead_of_claiming_mutation_without_tool(session_factory):
    async def run():
        with session_factory() as db:
            conversation = Conversation(); db.add(conversation); db.commit()
        provider = ScriptedProvider([
            ChatChunk(content="已经安排好了。", done=True),
            ChatChunk(tool_calls=[{"function": {"name": "create_task", "arguments": {
                "title": "守卫测试", "date": "2026-09-22", "start_time": "15:00", "duration_minutes": 30,
            }}}], done=True),
            ChatChunk(content="已创建。", done=True),
        ])
        registry, tool_executor = executor(session_factory)
        agent = AgentService(LLMService(provider), registry, tool_executor, session_factory)
        events = []
        outcome = await agent.run(conversation.id, [Message("system", "test"), Message("user", "明天安排任务")],
                                  GenerationOptions(), lambda event: events.append(event) or asyncio.sleep(0))
        assert outcome.affected_entities and outcome.content == "已创建。"
        assert any(event["event"] == "reset" for event in events)
    asyncio.run(run())


def test_conflict_free_slot_reschedule_complete_and_undo(session_factory):
    registry, tools = executor(session_factory)
    with session_factory() as db:
        conversation = Conversation(); db.add(conversation); db.commit(); key = conversation.id
    first = tools.execute(key, "create_task", {"title": "课程", "date": "2026-09-21", "start_time": "15:00", "duration_minutes": 60})
    assert first.success
    conflict = tools.execute(key, "create_task", {"title": "冲突", "date": "2026-09-21", "start_time": "15:30", "duration_minutes": 30})
    assert not conflict.success and conflict.error_code == "TIME_CONFLICT"
    slots = tools.execute(key, "get_free_slots", {"date": "2026-09-21", "earliest_time": "15:00", "latest_time": "18:00", "min_duration_minutes": 60})
    assert slots.data[0]["start_time"] == "16:00"
    moved = tools.execute(key, "reschedule_task", {"task_id": first.data["id"], "new_date": "2026-09-21", "new_start_time": "19:00"})
    assert moved.success and moved.data["start_time"] == "19:00"
    done = tools.execute(key, "complete_task", {"task_id": first.data["id"]})
    assert done.data["status"] == "completed"
    undone = tools.execute(key, "undo_last_action", {})
    assert undone.success and undone.data["status"] != "completed"


def test_destructive_action_uses_exact_saved_confirmation(session_factory):
    _, tools = executor(session_factory)
    with session_factory() as db:
        conversation = Conversation(); db.add(conversation); db.commit(); key = conversation.id
    created = tools.execute(key, "create_task", {"title": "待删", "date": "2026-09-21"})
    pending = tools.execute(key, "delete_task", {"task_id": created.data["id"]})
    assert pending.error_code == "CONFIRMATION_REQUIRED"
    result = tools.confirm(key, pending.confirmation["action_id"], True)
    assert result.success
    with session_factory() as db:
        assert db.get(Task, created.data["id"]).deleted_at


def test_schedule_and_replan_are_deterministic(session_factory):
    _, tools = executor(session_factory)
    with session_factory() as db:
        conversation = Conversation(); db.add(conversation); db.commit(); key = conversation.id
    scheduled = tools.execute(key, "schedule_task", {
        "title": "CS336", "date": "2026-09-22", "duration_minutes": 75, "preferred_period": "afternoon",
    })
    assert scheduled.success and scheduled.data["start_time"] == "12:00"
    conflict = tools.execute(key, "create_task", {
        "title": "托福", "date": "2026-09-21", "start_time": "15:00", "duration_minutes": 90,
    })
    replanned = tools.execute(key, "replan_day", {
        "date": "2026-09-21", "blocked_start": "15:00", "blocked_end": "18:00",
    })
    assert replanned.success and replanned.data["moved_tasks"]
    assert replanned.data["moved_tasks"][0]["start_time"] != conflict.data["start_time"]
    restored = tools.execute(key, "undo_last_action", {})
    assert restored.success and restored.data["restored_tasks"][0]["start_time"] == "15:00"


def test_large_replan_requires_confirmation(session_factory):
    _, tools = executor(session_factory)
    with session_factory() as db:
        conversation = Conversation(); db.add(conversation); db.commit(); key = conversation.id
    for index, start in enumerate(("14:00", "14:30", "15:00", "15:30")):
        assert tools.execute(key, "create_task", {
            "title": f"批量 {index}", "date": "2026-09-21", "start_time": start, "duration_minutes": 30,
        }).success
    pending = tools.execute(key, "replan_day", {
        "date": "2026-09-21", "blocked_start": "14:00", "blocked_end": "16:00",
    })
    assert pending.error_code == "CONFIRMATION_REQUIRED"
    assert pending.confirmation["affected_count"] == 4


def test_routine_tools_create_update_and_pause(session_factory):
    _, tools = executor(session_factory)
    with session_factory() as db:
        conversation = Conversation(); db.add(conversation); db.commit(); key = conversation.id
    created = tools.execute(key, "create_routine", {
        "name": "Agent Routine", "frequency": "daily", "start_date": "2026-09-21",
        "end_date": "2026-09-23", "preferred_time": "08:00", "estimated_duration": 25,
    })
    assert created.success
    updated = tools.execute(key, "update_routine", {
        "routine_id": created.data["id"], "preferred_time": "08:30",
    })
    assert updated.success and updated.data["preferred_time"] == "08:30"
    paused = tools.execute(key, "pause_routine", {"routine_id": created.data["id"]})
    assert paused.success and paused.data["active"] is False
    with session_factory() as db:
        routine = db.get(Routine, created.data["id"])
        assert routine and routine.active is False and routine.preferred_time == "08:30"


def test_add_to_calendar_phrase_exposes_create_task_and_normalizes_midnight(session_factory):
    registry, tools = executor(session_factory)
    agent = AgentService(None, registry, tools, session_factory)
    schemas = agent._tool_schemas("今天晚上24点学习，把它加到任务和日历中")
    assert "create_task" in {item["function"]["name"] for item in schemas}
    with session_factory() as db:
        conversation = Conversation(); db.add(conversation); db.commit(); key = conversation.id
    result = tools.execute(key, "create_task", {
        "title": "午夜任务", "date": "2026-09-21", "time": "24:00", "duration_minutes": 30,
    })
    assert result.success
    assert "2026-09-22 00:00–00:30，预计 30 分钟" in result.message
    assert (result.data["date"], result.data["start_time"], result.data["end_time"]) == (
        "2026-09-22", "00:00", "00:30")


def test_repeated_identical_tool_failure_stops_with_useful_message(session_factory):
    async def run():
        with session_factory() as db:
            conversation = Conversation(); db.add(conversation); db.commit()
        failed_call = ChatChunk(tool_calls=[{"function": {"name": "create_task", "arguments": {
            "title": "非法时间", "date": "2026-09-21", "start_time": "25:00",
        }}}], done=True)
        provider = ScriptedProvider([failed_call, failed_call])
        registry, tool_executor = executor(session_factory)
        agent = AgentService(LLMService(provider), registry, tool_executor, session_factory)
        outcome = await agent.run(
            conversation.id, [Message("system", "test"), Message("user", "把任务加上去")],
            GenerationOptions(), lambda event: asyncio.sleep(0))
        assert "无法执行这个操作" in outcome.content
        assert len(provider.requests) == 2
    asyncio.run(run())


def test_late_task_without_duration_is_created_before_midnight(session_factory):
    async def run():
        with session_factory() as db:
            conversation = Conversation(); db.add(conversation); db.commit()
        call = ChatChunk(tool_calls=[{"function": {"name": "create_task", "arguments": {
            "title": "学习cs336", "date": "2026-09-21", "time": "23:45", "duration_minutes": 60,
        }}}], done=True)
        provider = ScriptedProvider([call, ChatChunk(content="已经添加。", done=True)])
        registry, tool_executor = executor(session_factory)
        agent = AgentService(LLMService(provider), registry, tool_executor, session_factory)
        outcome = await agent.run(
            conversation.id,
            [Message("system", "test"), Message("user", "今天晚上23点45要学习cs336，在任务和日历中加上去")],
            GenerationOptions(), lambda event: asyncio.sleep(0))
        assert outcome.content == "已经添加。"
        with session_factory() as db:
            task = db.scalar(select(Task).where(Task.title == "学习cs336"))
            assert task and (task.start_time, task.end_time, task.estimated_duration) == ("23:45", "23:59", 14)
    asyncio.run(run())

import asyncio

from sqlalchemy import select

from app.agent.agent_service import AgentService, MANUAL
from app.agent.registry import build_registry
from app.agent.tool_executor import ToolExecutor
from app.agent.tools import PlanningTools
from app.agent import workspace_tools
from app.models import (AgentActionLog, CalendarEvent, ChatAttachment, Conversation, Goal,
                        KnowledgeDocument, LearningEntry, Milestone, Project, Routine, Task)
from app.services import attachments
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


def test_agent_manual_is_loaded_and_documents_every_tool(session_factory):
    registry, tool_executor = executor(session_factory)
    for name in registry.definitions:
        assert f"`{name}`" in MANUAL
    assert all(hasattr(PlanningTools, definition.handler) for definition in registry.definitions.values())
    assert len(registry.schemas()) == len(registry.definitions)
    agent = AgentService(None, registry, tool_executor, session_factory)
    with session_factory() as db:
        prompt = agent.system_prompt(db)
    assert "# DayMark Agent 功能与使用手册" in prompt
    assert "Task 的预计用时等于结束时间减开始时间" in prompt


def test_recurring_language_routes_to_create_routine(session_factory):
    registry, tool_executor = executor(session_factory)
    agent = AgentService(None, registry, tool_executor, session_factory)
    names = {item["function"]["name"] for item in agent._tool_schemas(
        "从明天到 10 月 1 日，每天 07:00 到 08:00 晨读")}
    assert "create_routine" in names and "create_task" not in names
    milestone_names = {item["function"]["name"] for item in agent._tool_schemas("修改里程碑截止日期")}
    assert {"get_projects", "get_milestones", "create_milestone",
            "update_milestone", "delete_milestone"} == milestone_names
    hierarchy_names = {item["function"]["name"] for item in agent._tool_schemas(
        "新建目标毕业设计，并在下面创建项目原型开发")}
    assert {"create_goal", "get_goals", "create_project"} <= hierarchy_names
    learning_names = {item["function"]["name"] for item in agent._tool_schemas(
        "记录今天学习 Attention 90 分钟，进度 80%")}
    assert "create_learning_entry" in learning_names and "create_task" not in learning_names
    event_names = {item["function"]["name"] for item in agent._tool_schemas("明天 10 点有个项目会议")}
    assert "create_event" in event_names
    knowledge_names = {item["function"]["name"] for item in agent._tool_schemas(
        "把刚上传的课件.pdf 保存到知识库")}
    assert "save_attachment_to_knowledge" in knowledge_names


def test_goal_domain_exposes_complete_tools_and_handles_colloquial_create(session_factory):
    registry, tool_executor = executor(session_factory)
    agent = AgentService(None, registry, tool_executor, session_factory)
    names = {item["function"]["name"] for item in agent._tool_schemas(
        "我要哦订一个目标就是10月2日考托福")}
    assert {"get_goals", "create_goal", "update_goal", "delete_goal"} <= names


def test_short_confirmation_inherits_recent_tool_intent(session_factory):
    registry, tool_executor = executor(session_factory)
    agent = AgentService(None, registry, tool_executor, session_factory)
    messages = [
        Message("system", "system"),
        Message("user", "我要哦订一个目标就是10月2日考托福"),
        Message("assistant", "请确认"),
        Message("user", "都行"),
        Message("assistant", "请再次确认"),
        Message("user", "确认"),
    ]
    routing_text = agent._routing_text(messages)
    assert "10月2日考托福" in routing_text
    names = {item["function"]["name"] for item in agent._tool_schemas(routing_text)}
    assert "create_goal" in names


def test_workspace_tools_cover_manual_page_operations(session_factory):
    _, tools = executor(session_factory)
    with session_factory() as db:
        conversation = Conversation(); db.add(conversation); db.commit(); key = conversation.id
    goal = tools.execute(key, "create_goal", {"name": "毕业设计", "target_date": "2026-12-31"})
    project = tools.execute(key, "create_project", {"name": "原型开发", "goal_id": goal.data["id"]})
    milestone = tools.execute(key, "create_milestone", {
        "name": "完成原型", "project_id": project.data["id"], "deadline": "2026-10-31"})
    event = tools.execute(key, "create_event", {
        "title": "组会", "start": "2026-09-22T10:00", "end": "2026-09-22T11:00"})
    learning = tools.execute(key, "create_learning_entry", {
        "date": "2026-09-21", "title": "复习 Attention", "project_id": project.data["id"],
        "duration_minutes": 90, "progress": 80})
    review = tools.execute(key, "save_daily_review", {
        "date": "2026-09-21", "actual_minutes": 90, "energy_level": 4,
        "project_minutes": {project.data["id"]: 90}})
    stats = tools.execute(key, "get_statistics", {"date": "2026-09-21"})
    setting = tools.execute(key, "update_settings", {"day_start": "08:30"})
    updated_goal = tools.execute(key, "update_goal", {"record_id": goal.data["id"], "status": "completed"})
    updated_event = tools.execute(key, "update_event", {"event_id": event.data["id"], "title": "项目组会"})
    updated_learning = tools.execute(key, "update_learning_entry", {
        "record_id": learning.data["id"], "progress": 100, "status": "completed"})
    progress = tools.execute(key, "get_progress", {})
    ai_setting = tools.execute(key, "update_ai_settings", {"mode": "local", "temperature": 0.2})
    export = tools.execute(key, "prepare_data_export", {})
    assert all(result.success for result in (goal, project, milestone, event, learning, review, stats,
                                              setting, updated_goal, updated_event, updated_learning,
                                              progress, ai_setting, export))
    assert stats.data["actual_minutes"] == 90 and setting.data["day_start"] == "08:30"
    assert updated_goal.data["status"] == "completed" and updated_event.data["title"] == "项目组会"
    assert updated_learning.data["progress"] == 100
    assert ai_setting.data["mode"] == "local" and export.data["download_url"] == "/api/export"
    with session_factory() as db:
        assert db.get(Goal, goal.data["id"]) and db.get(Project, project.data["id"])
        assert db.get(Milestone, milestone.data["id"]) and db.get(LearningEntry, learning.data["id"])


def test_uploaded_chat_attachment_can_be_saved_to_knowledge(session_factory, tmp_path, monkeypatch):
    upload_dir, knowledge_dir = tmp_path / "uploads", tmp_path / "knowledge"
    upload_dir.mkdir(); monkeypatch.setattr(attachments, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(workspace_tools, "KNOWLEDGE_DIR", knowledge_dir)
    content = b"# Lecture notes\nAttention and transformers"
    (upload_dir / "stored.md").write_bytes(content)
    with session_factory() as db:
        conversation = Conversation(); db.add(conversation); db.flush()
        db.add(ChatAttachment(conversation_id=conversation.id, filename="lecture.md",
                              media_type="text/markdown", size_bytes=len(content),
                              storage_name="stored.md", extracted_text=content.decode()))
        db.commit(); key = conversation.id
    _, tools = executor(session_factory)
    result = tools.execute(key, "save_attachment_to_knowledge", {
        "filename": "lecture.md", "knowledge_date": "2026-09-21", "document_type": "note"})
    assert result.success and result.data["processing_status"] == "ready"
    with session_factory() as db:
        row = db.get(KnowledgeDocument, result.data["id"])
        assert row.extracted_text.startswith("# Lecture")
        assert (knowledge_dir / row.storage_path).read_bytes() == content


def test_non_task_deletes_use_saved_confirmation(session_factory):
    _, tools = executor(session_factory)
    with session_factory() as db:
        conversation = Conversation(); db.add(conversation); db.commit(); key = conversation.id
    goal = tools.execute(key, "create_goal", {"name": "临时目标"})
    pending = tools.execute(key, "delete_goal", {"record_id": goal.data["id"]})
    assert pending.error_code == "CONFIRMATION_REQUIRED"
    deleted = tools.confirm(key, pending.confirmation["action_id"], True)
    assert deleted.success
    with session_factory() as db:
        assert db.get(Goal, goal.data["id"]) is None


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


def test_write_tool_is_idempotent_within_request(session_factory):
    _, tools = executor(session_factory)
    with session_factory() as db:
        conversation = Conversation(); db.add(conversation); db.commit(); key = conversation.id
    arguments = {"title": "只创建一次", "date": "2026-09-22", "start_time": "10:00", "duration_minutes": 30}
    first = tools.execute(key, "create_task", arguments, request_id="request-1", provider="deepseek", model="deepseek-flash")
    second = tools.execute(key, "create_task", arguments, request_id="request-1", provider="deepseek", model="deepseek-flash")
    assert first.success and second.success and first.data["id"] == second.data["id"]
    with session_factory() as db:
        assert len(list(db.scalars(select(Task).where(Task.title == "只创建一次")))) == 1
        log = db.scalar(select(AgentActionLog).where(AgentActionLog.request_id == "request-1"))
        assert (log.provider, log.model, len(log.fingerprint)) == ("deepseek", "deepseek-flash", 64)


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


def test_timetable_routes_to_batch_import_and_allows_date_clarification(session_factory):
    async def run():
        registry, tool_executor = executor(session_factory)
        agent = AgentService(LLMService(ScriptedProvider([
            ChatChunk(content="课表里没有学期日期，请提供开始和结束日期？", done=True),
        ])), registry, tool_executor, session_factory)
        schemas = agent._tool_schemas("把[附件：schedule.pdf]里的课表导入日历")
        assert {item["function"]["name"] for item in schemas} == {"import_timetable"}
        with session_factory() as db:
            conversation = Conversation(); db.add(conversation); db.commit()
        outcome = await agent.run(
            conversation.id,
            [Message("system", "test"), Message("user", "把附件课表导入日历")],
            GenerationOptions(), lambda event: asyncio.sleep(0))
        assert "请提供开始和结束日期" in outcome.content
    asyncio.run(run())


def test_timetable_import_requires_confirmation_and_creates_weekly_routines(session_factory):
    _, tools = executor(session_factory)
    with session_factory() as db:
        conversation = Conversation(); db.add(conversation); db.commit(); key = conversation.id
    arguments = {
        "start_date": "2026-09-22", "end_date": "2026-12-15",
        "courses": [
            {"name": "Operating Systems", "weekdays": ["monday"], "start_time": "09:00", "end_time": "10:15", "location": "C101"},
            {"name": "Machine Learning", "weekdays": ["wednesday", "friday"], "start_time": "14:00", "end_time": "15:30"},
        ],
    }
    pending = tools.execute(key, "import_timetable", arguments)
    assert pending.error_code == "CONFIRMATION_REQUIRED"
    assert pending.confirmation["affected_count"] == 2
    assert "Operating Systems" in pending.confirmation["description"]
    with session_factory() as db:
        assert not list(db.scalars(select(Routine)))
    result = tools.confirm(key, pending.confirmation["action_id"], True)
    assert result.success and len(result.affected_entities) == 2
    with session_factory() as db:
        routines = list(db.scalars(select(Routine).order_by(Routine.name)))
        assert [row.name for row in routines] == ["Machine Learning", "Operating Systems"]
        assert routines[0].weekdays == [2, 4]
        assert routines[1].description == "C101"

# 本地 AI Agent 架构

## 执行链

DayMark 在原有 Next.js / FastAPI / SQLAlchemy 架构上增加独立 Agent 层，不建立第二套任务数据，也不允许模型执行 SQL。

```text
AI Chat → Conversation Service → Agent Service → Qwen3 Tool Calling
        → Tool Registry → Tool Executor → 既有 Planner / Scheduler / Calendar Service
        → SQLAlchemy → SQLite → affected_entities → 前端 refresh()
```

模型负责理解意图和选择工具；日期冲突、空闲时间和改期计算由确定性 Python 服务完成。每轮注入 `current_datetime` 与 `Asia/Shanghai` 时区。工具参数先经过 Pydantic 严格校验，日期和时间最终只能使用 `YYYY-MM-DD` 与 `HH:MM`。

Agent Loop 最多执行 8 步。模型返回 tool call 后，执行器调用注册工具，再把统一 Tool Result 作为 `tool` message 交还模型，直到得到最终中文回答。若写入请求未发生真实工具调用，系统会丢弃模型声称成功的正文并重试；达到上限则安全失败，不伪造执行结果。

## 模块职责

- `backend/app/agent/agent_service.py`：循环、当前时间、会话实体引用、按意图缩小工具集合、防止假执行。
- `backend/app/agent/tool_registry.py` 与 `registry.py`：统一 JSON Schema、权限和用户可见状态文案。
- `backend/app/agent/tool_executor.py`：参数验证、权限、确认、调用日志和异常净化。
- `backend/app/agent/tools.py`：Task / Calendar / Routine / Planner 工具适配，只调用既有业务服务。
- `backend/app/agent/planner_service.py`：冲突检测、空闲时段合并和 first-fit 调度。
- `backend/app/prompts/agent_system_prompt.txt`：执行型 Agent 规则。
- `backend/app/services/conversation.py`：聊天历史、SSE、Agent 调用、停止与持久化。
- `backend/app/services/llm/`：Ollama provider 和模型协议，不硬编码工具。

## 工具与权限

READ 自动执行：`get_today_tasks`、`get_tasks`、`get_calendar`、`get_free_slots`、`get_routines`、`get_upcoming_deadlines`。

WRITE 自动执行并写 `AgentActionLog`：`create_task`、`update_task`、`reschedule_task`、`complete_task`、`cancel_task`、`create_routine`、`update_routine`、`pause_routine`、`schedule_task`、`replan_day`、`undo_last_action`。

DESTRUCTIVE 必须确认：`delete_task`。一次 `replan_day` 影响超过 3 个任务时也动态升级为需确认操作。后端把精确工具名和参数保存到 `PendingAgentAction`，确认接口执行保存的动作，不让模型重新生成参数。

每个 Tool Result 统一返回 `success`、`message`、`data`、`affected_entities`，失败另含 `error_code`。Python 异常文本不会直接暴露给模型或页面。

## Calendar、刷新和撤销

现有 `PlannerService` 在每次 Task 创建或变更后同步唯一的 `CalendarEvent`，因此 Calendar 不维护一份会漂移的日程副本。独立 Calendar Event 同样参与冲突检测；无时间 Task 不占整天，独立全天事件占据全天。

SSE 增加 `tool_status`、`tool_result` 和 `reset`。前端收到 `affected_entities` 后调用现有 `refresh()`，同时重取 bootstrap、today、statistics、progress 并递增日历 revision；无需 React Query。

写操作保存参数、before/after 快照、状态和错误。`undo_last_action` 可撤销 create/schedule/update/reschedule/complete/replan；创建类撤销为软删除，其余按快照恢复并再次走 Planner 同步。

## 数据与运行边界

迁移 `0002` / `0003` 保存会话、消息与模型设置；`0004` 新增 `agent_action_logs` 和 `pending_agent_actions`。模型、Ollama 程序、SQLite 与日志均在项目目录内且不提交 Git。

默认模型为 `qwen3:8b`，context 8192、temperature 0.6、Thinking Off。Ollama 离线时 AI health 显示不可用，Task、Calendar、Routine 和统计 API 继续工作。当前没有 RAG、知识库、文件上传、多 Agent、长期自动规划或云端推理。

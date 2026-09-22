# DeepSeek Cloud + Local Qwen Agent 架构

## 执行链

DayMark 在原有 Next.js / FastAPI / SQLAlchemy 架构上增加独立 Agent 层，不建立第二套任务数据，也不允许模型执行 SQL。

```text
AI Chat → Conversation Service → Agent Service → Provider Router
        → DeepSeek Cloud（默认）或 Local Qwen（降级/手动）
        → Tool Registry → Tool Executor → 既有 Planner / Scheduler / Calendar Service
        → SQLAlchemy → SQLite → affected_entities → 前端 refresh()
```

模型负责理解意图和选择工具；日期冲突、空闲时间和改期计算由确定性 Python 服务完成。每轮注入 `current_datetime` 与 `Asia/Shanghai` 时区。工具参数先经过 Pydantic 严格校验，日期和时间最终只能使用 `YYYY-MM-DD` 与 `HH:MM`。

Agent Loop 最多执行 8 步。模型返回 tool call 后，执行器调用注册工具，再把统一 Tool Result 作为 `tool` message 交还模型，直到得到最终中文回答。若写入请求未发生真实工具调用，系统会丢弃模型声称成功的正文并重试；达到上限则安全失败，不伪造执行结果。

## 模块职责

- `backend/app/agent/agent_service.py`：循环、当前时间、会话实体引用、按意图缩小工具集合、防止假执行。
- `backend/app/agent/tool_registry.py` 与 `registry.py`：统一 JSON Schema、权限和用户可见状态文案。
- `backend/app/agent/tool_executor.py`：参数验证、权限、确认、调用日志和异常净化。
- `backend/app/agent/tools.py` 与 `workspace_tools.py`：覆盖页面可人工操作的数据，复用既有 Schema、Service 和业务校验。
- `backend/app/agent/planner_service.py`：冲突检测、空闲时段合并和 first-fit 调度。
- `backend/app/prompts/agent_system_prompt.txt`：执行型 Agent 规则。
- `backend/app/services/conversation.py`：聊天历史、SSE、Agent 调用、停止与持久化。
- `backend/app/services/llm/base.py`：Provider 共用消息、流式结果和错误协议。
- `backend/app/services/llm/deepseek_provider.py`：DeepSeek Chat Completions、SSE、Tool Calls 与 thinking 上下文。
- `backend/app/services/llm/ollama_provider.py`：本地 Qwen/Ollama 适配器。
- `backend/app/services/llm/router.py`：按请求选择 Provider 并执行安全降级；不包含工具或业务逻辑。

## 工具与权限

READ 查询自动执行，覆盖 Task、Calendar、Routine、Goal、Project、Milestone、学习档案、知识库、每日复盘、统计、设置和通知。

WRITE 创建与修改自动执行并写 `AgentActionLog`。每个工具复用页面对应的 Schema、关联校验和 Service；知识库工具只能复制当前对话已上传的附件，不能读取任意路径。完整工具名和行为以运行时加载的 [Agent 手册](../backend/app/prompts/agent_manual.md) 为准。

所有 `delete_*` 工具均为 DESTRUCTIVE，必须确认。课表导入始终确认；一次 `replan_day` 影响超过 3 个任务时也动态升级为需确认操作。后端把精确工具名和参数保存到 `PendingAgentAction`，确认接口执行保存的动作，不让模型重新生成参数。

每个 Tool Result 统一返回 `success`、`message`、`data`、`affected_entities`，失败另含 `error_code`。Python 异常文本不会直接暴露给模型或页面。

## Calendar、刷新和撤销

现有 `PlannerService` 在每次 Task 创建或变更后同步唯一的 `CalendarEvent`，因此 Calendar 不维护一份会漂移的日程副本。独立 Calendar Event 同样参与冲突检测；无时间 Task 不占整天，独立全天事件占据全天。

SSE 增加 `tool_status`、`tool_result` 和 `reset`。前端收到 `affected_entities` 后调用现有 `refresh()`，同时重取 bootstrap、today、statistics、progress 并递增日历 revision；无需 React Query。

写操作保存参数、before/after 快照、状态、错误、`request_id`、Provider、模型与参数指纹。相同请求再次发出同一个写调用时直接返回第一次结果，不重复写库。`undo_last_action` 可撤销 create/schedule/update/reschedule/complete/replan；创建类撤销为软删除，其余按快照恢复并再次走 Planner 同步。

## Provider 路由与降级

- `Auto`：先调用 DeepSeek。只有网络、超时、限流、服务不可用或未配置 Key 这类可恢复错误，且本轮尚无成功 WRITE 时，才切换到本地 Qwen。
- `DeepSeek`：固定使用云端，失败时明确报错，不自动降级。
- `Local Qwen`：固定使用项目内 Ollama，不发送云端请求。

一旦 WRITE 已成功，后续 DeepSeek 故障不会重跑 Agent 或切换模型；系统返回“操作已经完成，但最终回复失败”，避免同一任务、日历事件或 Routine 被创建两次。READ 调用不阻止安全降级。

Thinking 内容只存在于当前 Provider 调用的内存上下文。DeepSeek 工具循环会按官方协议回传 `reasoning_content`，但 SSE、聊天正文和数据库消息都不显示或保存它。

## 数据与运行边界

迁移 `0002` / `0003` 保存会话、消息与模型设置；`0004` 新增 Agent 操作表；`0006` 增加 Provider 模式和请求级幂等元数据。模型、Ollama 程序、SQLite、日志与 `.env` 均不提交 Git。

默认模式为 `Auto`，云端模型 `deepseek-flash`，本地后备 `qwen3:8b`。API Key 只从后端环境读取，状态接口只返回 `configured` 布尔值。两个 Provider 都不可用时，所有普通页面和 API 仍继续工作。系统包含知识库文件归档，但不包含向量 RAG、多 Agent 或长期自动规划。

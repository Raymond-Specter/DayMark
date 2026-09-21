# AI Agent 交付清单

## 新增

- `backend/app/agent/`：Agent Loop、权限枚举、Pydantic Tool Schema、注册表、执行器、Task/Calendar/Routine 工具和确定性 Planner。
- `backend/app/prompts/agent_system_prompt.txt`：执行型中文系统提示。
- `backend/migrations/versions/0004_agent_actions.py`：操作日志与待确认动作。
- `backend/tests/test_agent.py`：最小闭环、假执行守卫、冲突、调度、改期、确认、撤销和批量确认测试。

## 修改

- `backend/app/api/ai.py`：装配 Agent，增加确认与操作日志 API。
- `backend/app/services/conversation.py`：聊天生成改走 Agent Loop，SSE 返回工具状态、影响实体和确认数据。
- `backend/app/services/llm/ollama_provider.py`：向 Ollama 传递 Tool Schema 并读取 tool calls。
- `backend/app/models.py`：增加 `AgentActionLog`、`PendingAgentAction`。
- `frontend/components/assistant/` 与 `frontend/lib/ai.ts`：工具执行状态、确认卡片、SSE 新事件。
- `frontend/app/page.tsx`：Agent 写入后调用现有全局 `refresh()`，日历和统计自动更新。
- 架构、API、数据库、目录、README 和使用文档同步更新。

原有 Goal / Project / Milestone / Task / Routine / Calendar 表与业务 Service 均被复用。没有新增平行数据体系，模型没有 SQL 或 ORM 访问权。

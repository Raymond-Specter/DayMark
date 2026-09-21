# 本地 AI Agent 验收记录

日期：2026-09-21。模型：项目内 Ollama 0.34.2 / qwen3:8b，8192 context，Thinking Off。

## 自动检查

- Agent 定向测试：6 passed。
- 后端全量测试：94 passed（另有 2 条第三方依赖弃用警告）。
- Alembic：数据库位于 `0004 (head)`，迁移差异检查通过。
- Frontend TypeScript 与 Next.js production build：通过。

## 真实模型案例

| 测试 | 真实结果 |
| --- | --- |
| 1. 明天 15:00 安排 90 分钟托福 | 调用 `create_task`，Task 与 Calendar Event 均创建为 15:00–16:30 |
| 2. 今天有哪些任务 | 调用 `get_today_tasks`，回答来自 SQLite 中的真实任务 |
| 3. 明天下午找 75 分钟 CS336 | 调用 `schedule_task`，确定性找到 12:00–13:15 并创建 |
| 4. 把刚才 CS336 改到晚上 | 根据会话操作引用定位正确 ID，调用 `reschedule_task` 改到 18:00–19:15 |
| 5. 完成今天托福 | 调用 `complete_task`，真实状态变为 completed |
| 6. 撤销刚才操作 | 调用 `undo_last_action`，同一任务恢复 pending |
| 7. 今天 15:00–18:00 有事并重排 | 调用 `replan_day`，冲突任务从 15:00 移到 09:30–10:30，无 unresolved |
| 8. 创建重叠任务 | 14:15 请求与 14:00–14:30 事项冲突，返回 TIME_CONFLICT，未覆盖日程 |
| 9. 关闭 Ollama | Today 与 Calendar API 继续成功；AI health 显示 Ollama/Model unavailable；重启后恢复 Online |
| 10. 浏览器刷新 | 从聊天创建的 2026-09-23 10:00 任务立即出现在 Calendar，整页刷新后仍存在 |

真实请求还验证了聊天中的“正在创建/正在重排/已完成”状态、`affected_entities` 自动刷新和写操作日志。原始机器验收输出保存在 Git 忽略的 `.runtime/agent-live-results.json` 与 `.runtime/agent-replan-results.json`。

## 已修复的真实模型问题

Qwen3 8B 在长会话中曾模仿之前的文字回答而不调用 `complete_task`。最终实现对动作轮次只保留当前请求，并把最近成功操作以已验证实体引用注入系统提示；同时按意图只暴露必要工具。复测完成和撤销分别约 3.5 秒与 2.7 秒，均产生真实 Tool Result。无工具结果时系统仍会清除正文并安全失败。

## 测试数据

机器验收任务标题均带 `Agent验收` 或 `Agent界面刷新验收`。验收结束后已通过应用 API 软删除 7 个测试任务，并删除 4 个测试会话；真实用户任务未被修改。测试前数据库备份为 `data/backups/planner-before-agent-20260921-173441.db`。

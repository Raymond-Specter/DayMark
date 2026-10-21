# AI Agent 使用说明

## DeepSeek 配置

最简单的方式是在 AI Assistant 右上角打开“模型设置”，在 `DeepSeek API Key` 密码框中粘贴 Key，然后点击“保存 Key 与设置”。后端会写入项目根目录 `.env` 并立即启用，页面不会回显 Key。

复制 `.env.example` 中的 DeepSeek 字段到项目根目录 `.env`，只填写后端变量：

```dotenv
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_TIMEOUT_SECONDS=120
DEEPSEEK_THINKING_DEFAULT=false
LLM_DEFAULT_MODE=auto
```

保存后重启后端。真实 Key 不要填写到网页、localStorage、数据库或 Git；页面只会显示 Key 是否已配置。

## 启动

首次安装项目内 Ollama 和模型：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_ollama.ps1 -Install -Start -Pull
```

日常启动：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1
```

当前电脑因 Windows 保留 11434 所在端口段，在根目录 `.env` 使用 `OLLAMA_BASE_URL=http://127.0.0.1:11535`。其他电脑一般可使用默认 11434。程序位于 `runtime/ollama`，模型位于 `models/ollama`，不会进行系统级安装。

## 使用方式

打开 `http://127.0.0.1:3000/assistant`。可以直接说：

- “明天下午3点创建90分钟托福刷题。”
- “找个明天下午的空闲时间安排75分钟CS336。”
- “把刚才创建的CS336改到晚上。”
- “完成今天的托福任务。”
- “撤销刚才那个操作。”
- “今天下午3点到6点有事，把冲突任务重新安排。”
- “从明天到 10 月 1 日，每天 07:00–08:00 晨读。”
- “新建目标‘完成毕业设计’，并在下面创建项目‘原型开发’。”
- “记录今天学习 Attention 90 分钟，进度 80%。”
- “把刚上传的 lecture.pdf 保存到知识库。”
- “保存今天复盘：实际投入 120 分钟，精力 4。”

聊天区会显示“正在读取日历”“正在创建任务”等状态。成功写入后 Today、Task、Calendar、Routine 和统计数据自动刷新。明确时间发生冲突时不会覆盖原日程，而会报告冲突并询问是否换时间。

删除任务和影响超过 3 个任务的单次改期会显示确认卡片。确认后后端执行保存的原始参数；取消则不修改数据。

## 按每日时长规划与追问

例如“以后每天学5小时托福，不动原来的安排”：Agent 先查询日历与重复规则，缺少起止日期、可用时段、是否分段及最短分段时，通过问题卡片让用户选择或自填。未选的选项不会被当成答案，也不会自动把全天空白当成学习时间。

条件齐全后，`plan_daily_tasks` 按每天的真实占用计算新增时段，支持一天分成多段、每天时间不同。确认卡片显示逐日时间与分钟数；点击确认才统一创建任务，保留原有任务、独立事项和重复规则。任一天无法达到目标就显示缺口并追问，不自动少排或挪动旧任务。确认前日历已变化时整批拒绝，重新预览。未被后续修改的整批新增可通过 `undo_last_action` 撤销。

已有托福等同类安排时，先确认是“每天总共5小时”还是“额外新增5小时”；只有经用户确认的真实任务ID（`counted_task_ids`）会计入目标，各天分别补足，不按标题猜测。预览会分别显示已计入分钟与新增分钟。新用户消息会使旧规划预览失效。

单次规划最多31天，用户需明确本次截止日；当前不支持无限期自动续排。固定钟点的重复安排仍使用 Routine。通用 `ask_user` 支持1至4个问题、可选项和自由输入，刷新后恢复待答问题和规划预览。通过 `POST /api/ai/chat` 提交 `clarification_id` 与 `answers`，后端核验会话归属并将答案写入聊天上下文。普通文字回复也能继续对话。

## API 与事件

- `GET /api/ai/health`：DeepSeek、Ollama、Agent、当前模式和设置状态。
- `GET /api/ai/providers/status`：两个 Provider 的可用状态，不返回 Key。
- `POST /api/ai/chat`：保留流式 SSE。
- `POST /api/ai/confirm/{action_id}`：确认或取消保存的操作与规划预览。
- `GET /api/ai/conversations/{id}/actions`：最近 100 条 Agent 写操作日志。

SSE 事件包括 `start`、`provider_status`、`delta`、`reset`、`tool_status`、`tool_result`、`done`、`error`。`tool_result` 与 `done` 包含受影响实体、可选的 `confirmation` 和 `clarification`。

## 验证命令

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini check
Set-Location frontend
npm.cmd run typecheck
npm.cmd run build
```

真实模型验收记录见 [ai_verification.md](ai_verification.md)。自动测试使用模拟 Provider，不依赖本地模型在线。

## 当前限制

- 未配置 DeepSeek Key 时，Auto 会使用本地 Qwen；DeepSeek 模式会明确提示配置 Key。
- Qwen3 8B 是小型本地模型，复杂或含糊指令可能需要更明确的任务名、日期或时间。
- Agent 可以通过受控工具操作页面中的 Task、Calendar、Routine、Goal、Project、Milestone、学习档案、知识库附件、每日复盘、统计、时区/默认开始时间和通知；删除等破坏性操作仍需确认。
- 调度采用确定性 first-fit，不做复杂最优化，也不会自主制定长期计划。
- 操作引用主要来自当前会话最近成功动作；跨会话含糊说“刚才那个”时应补充任务名。
- 已有 Knowledge Base 文件归档和筛选，但没有向量 RAG、多 Agent 或长期自主规划。

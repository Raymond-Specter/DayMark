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

聊天区会显示“正在读取日历”“正在创建任务”等状态。成功写入后 Today、Task、Calendar、Routine 和统计数据自动刷新。明确时间发生冲突时不会覆盖原日程，而会报告冲突并询问是否换时间。

删除任务和影响超过 3 个任务的单次改期会显示确认卡片。确认后后端执行保存的原始参数；取消则不修改数据。

## API 与事件

- `GET /api/ai/health`：DeepSeek、Ollama、Agent、当前模式和设置状态。
- `GET /api/ai/providers/status`：两个 Provider 的可用状态，不返回 Key。
- `POST /api/ai/chat`：保留流式 SSE。
- `POST /api/ai/confirm/{action_id}`：确认或取消保存的破坏性动作。
- `GET /api/ai/conversations/{id}/actions`：最近 100 条 Agent 写操作日志。

SSE 事件包括 `start`、`provider_status`、`delta`、`reset`、`tool_status`、`tool_result`、`done`、`error`。`done` 包含本轮 `affected_entities` 和可选 `confirmation`。

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
- Agent 只操作 Task、Calendar 与 Routine，不修改 Goal；Project 仅作为可选关联 ID。
- 调度采用确定性 first-fit，不做复杂最优化，也不会自主制定长期计划。
- 操作引用主要来自当前会话最近成功动作；跨会话含糊说“刚才那个”时应补充任务名。
- 没有 RAG、Knowledge Base 或多 Agent。

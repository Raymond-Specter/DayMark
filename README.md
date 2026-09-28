<div align="center">

# DayMark

### Plan your day. Keep your progress.

一个将时间规划、日历、学习记录与 AI 操作连接起来的个人工作空间。

![Next.js](https://img.shields.io/badge/Next.js-16-111111?style=flat-square&logo=nextdotjs&logoColor=white)
![React](https://img.shields.io/badge/React-19-111111?style=flat-square&logo=react&logoColor=61DAFB)
![FastAPI](https://img.shields.io/badge/FastAPI-Python_3.10%2B-111111?style=flat-square&logo=fastapi&logoColor=009688)
![SQLite](https://img.shields.io/badge/SQLite-Local_storage-111111?style=flat-square&logo=sqlite&logoColor=8AB4F8)

[功能](#功能) · [快速开始](#快速开始) · [AI Assistant](#ai-assistant) · [开发](#开发)

<img src="frontend/public/images/gargantua-poster.jpg" alt="DayMark 首页使用的 Gargantua 黑洞背景" width="100%" />

</div>

## 关于 DayMark

DayMark 是一个本地优先的个人规划与学习记录应用。打开首页，看到今天要做的事；切换到日历，安排时间；在目标与项目中查看整体进度，再把实际投入和学习资料留在同一个工作空间里。

它提供规划的框架，具体内容由你决定。没有预置课程、考试或求职路线，也不会替你改动优先级。

## 功能

| 模块 | 可以做什么 |
| --- | --- |
| **Today** | 查看今日任务、完成进度、计划时长、昨日未完成事项和临近截止任务 |
| **Calendar** | 日 / 周 / 月视图，拖动任务调整日期和时间，管理独立日历事项 |
| **Goals & Projects** | 用 Goal → Project → Milestone → Task 组织规划，查看真实完成进度 |
| **Tasks & Routines** | 创建、编辑、完成、延期和取消任务；支持重复规则及简单依赖 |
| **AI Assistant** | 用自然语言操作规划数据，支持 DeepSeek Cloud 和本地 Qwen |
| **Learning Archive** | 记录学习、阅读、作业和研究的实际投入、进展、反思与下一步 |
| **Knowledge Base** | 保存资料，按日期、项目和类型归档；聊天附件可通过 Agent 保存到知识库 |
| **Daily Review & Insights** | 记录每日精力与实际投入，查看完成率、时间分布和计划 / 实际对比 |

界面提供午夜黑（深色与视频首页）、樱花粉（奶白、柔粉与花形装饰）和莫兰迪（暖灰、鼠尾草绿与几何装饰）三种风格，可在设置中即时切换，选择保存在本机浏览器。默认英文，可切换中文；语言切换不会翻译你自己输入的内容。

## 快速开始

当前启动脚本适用于 **Windows + PowerShell**，需要 **Python 3.10+** 和 **Node.js 22+**。

```powershell
git clone https://github.com/Raymond-Specter/DayMark.git
cd DayMark

# 首次安装：依赖、数据库迁移和前端构建
powershell -ExecutionPolicy Bypass -File .\setup.ps1

# 启动服务并打开网页
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

打开 **[http://127.0.0.1:3000](http://127.0.0.1:3000)** 即可使用。AI 是可选功能，不配置模型也可以手动管理规划。

后续只需运行 `start.ps1`。关闭浏览器或终端不会停止服务；电脑关机或重启后，需要再次启动。

```powershell
.\start.ps1 -NoBrowser   # 后台启动，不打开浏览器
.\stop.ps1              # 停止服务，保留数据
.\backup.ps1            # 备份数据库
```

## AI Assistant

AI 不只用于聊天，也可以通过工具创建和修改任务、重复规则、目标、项目、学习记录等内容。每轮提供全部已注册工具，由模型结合近期对话选择操作，无需使用固定句式。

```text
明天 15:00–16:30 学习 Transformer，加入任务和日历。

从明天起，每周一到周五 07:00–08:00 阅读，持续到 10 月 31 日。

把刚上传的 lecture.pdf 保存到知识库。
```

Task 创建后会进入日历。已有记录的操作使用真实 ID，写入经过参数验证和业务服务；时间冲突会返回错误，删除、课表导入及大范围改期需要确认。只有工具执行成功后，Agent 才应报告操作完成。

### DeepSeek Cloud

在 **AI Assistant → 模型设置** 中填写并保存自己的 DeepSeek API Key，选择 `DeepSeek` 或 `Auto` 模式即可。也可以在根目录 `.env` 设置 `DEEPSEEK_API_KEY` 后重启；变量说明见 [.env.example](.env.example)。

API Key 保存在本机 `.env`，不会被接口回显，也不会写进聊天记录或 Git。使用云端模型时，对话及其附件文本会发送给所选模型服务；未参与对话的知识库资料不会自动上传。

### Local Qwen

本地模式使用项目目录内的 Ollama 和 `qwen3:8b`，首次安装需要下载数 GB 的模型文件。

```powershell
# 首次安装并下载模型
powershell -ExecutionPolicy Bypass -File .\scripts\setup_ollama.ps1 -Install -Start -Pull

# 后续启动本地模型与应用
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1
```

`Auto` 优先使用 DeepSeek；发生可恢复错误、且本轮尚未成功写入时，才会降级到本地 Qwen。完整工具集会增加上下文开销，小型本地模型的理解和执行可靠性仍受模型能力、上下文长度与硬件影响。

### PDF、OCR 与课表

聊天支持文本、Markdown、CSV、JSON、常见代码文件、DOCX 和 PDF；每次最多上传 **3 个文件**，单个文件不超过 **10 MB**。

PDF 优先提取文字层，扫描版 PDF 使用本地 OCR。课表解析会结合文字坐标整理星期列；识别结果仍需核对。提供学期起止日期和明确上下课时间后，可以让 Agent 批量导入课表，确认预览后生成每周重复规则。

<details>
<summary>配置扫描 PDF 的 OCR</summary>

电脑需安装 Tesseract，并提供 `pdftoppm`（MiKTeX / Poppler）。运行以下命令准备项目内 OCR 模型：

```powershell
.\scripts\setup_ocr.ps1 -DirectNetwork
```

仅有“第 1–2 节”而没有具体钟点的课表，需要补充学校节次时间表。缺少学期日期或识别不清时，Agent 会询问，不会自行猜测。

</details>

## 数据与运行说明

规划记录保存在 SQLite，上传资料保存在本机项目的数据目录。Git 不包含你的数据库、附件、API Key 或本地模型。

| 路径 | 内容 |
| --- | --- |
| `data/planner.db` | 规划数据库 |
| `data/backups/` | 数据库备份 |
| `logs/` | 服务日志 |
| `runtime/ollama/` | 项目内 Ollama |
| `models/ollama/` | 本地模型 |

<details>
<summary>备份、更新与常见问题</summary>

- **网页打不开 / Failed to fetch**：先运行 `start.ps1`，确认前后端服务已启动，再查看 `logs/`。端口被未知进程占用时，启动脚本不会替你停止该进程。
- **修改代码后仍显示旧界面**：生产服务不会自动加载源码修改。先停止服务，重新运行 `setup.ps1` 完成构建，再启动。
- **更新应用**：先运行 `backup.ps1`，停止服务，更新代码，再执行 `setup.ps1` 和 `start.ps1`。
- **数据库备份**：使用 `backup.ps1` 的 SQLite 在线备份，不要在运行时只复制 `.db` 文件；WAL 中可能还有未写回的数据。恢复前停止服务并保留当前数据，旧备份不能混用现有 `-wal` / `-shm` 文件。
- **文件备份**：数据库备份不等于附件备份，上传的文件也需要另行保存。定期把备份复制到其他磁盘。
- **安装时代理失效**：网络可以直连时，可运行 `setup.ps1 -DirectNetwork`；只调整本次安装的代理设置，保留 TLS 验证。

</details>

## 当前范围

- 目前是**单人本机应用**，只监听 `127.0.0.1`，尚未提供账号登录、多用户隔离或公网部署配置。
- 提醒支持准时及提前 10 / 30 / 60 / 1440 分钟。网页关闭、电脑睡眠或服务停止时，不能保证系统级实时通知；站内通知记录可在下次打开时查看。
- Google Calendar 尚未接入。
- 未完成任务不会自动删除或改期。重复任务默认提前生成 30 天，支持简单依赖；单次任务在同一天内安排。
- AI 不会自主制定长期路线；模糊指代、缺失信息和 OCR 错误仍可能需要你补充或确认。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Next.js · React · TypeScript · FullCalendar |
| 后端 | FastAPI · Pydantic · SQLAlchemy |
| 数据 | SQLite · Alembic |
| AI | DeepSeek API · Ollama / Qwen3 · 工具调用 |
| 文档解析 | PDF 文字提取 · Tesseract OCR |

## 开发

```powershell
# 后端测试与迁移检查（在项目根目录）
.\.venv\Scripts\python.exe -m pytest backend\tests -q
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini check

# 前端检查与构建
cd frontend
npm.cmd run typecheck
npm.cmd run build
```

后端接口文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。前端通过同源 `/api` 代理访问后端。

前端开发模式使用 `npm.cmd run dev`，需先启动后端并停止占用 3000 端口的生产前端。更多模型配置见 [AI 使用说明](docs/ai_usage.md)。

应用内 Agent 的能力说明维护在 [agent_manual.md](backend/app/prompts/agent_manual.md)。修改用户功能、工具或工作流程时，请同步更新手册。

---

<div align="center">

**DayMark** · Every step leaves a trace.

</div>

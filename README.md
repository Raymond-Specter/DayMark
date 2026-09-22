# DayMark — Personal Planning System

一个在自己电脑上运行的个人规划系统。打开后先看今日行动和未完成事项，再查看 Goal → Project → Milestone 的整体进度。所有目标、项目和重复规则均由你创建，初始数据库为空，不预设课程、考试或求职安排，也不会用 AI 改动你的优先级。

## 启动

需要 Windows、PowerShell、Python 3.10+ 和 Node.js 22+。在项目目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

首次安装会下载依赖、迁移 SQLite 数据库并构建前端。后续只需 `start.ps1`；修改代码或更新依赖后重新执行 `setup.ps1`。启动脚本会在后台运行服务，并打开 [本地应用](http://127.0.0.1:3000)。关闭终端不会关闭应用。电脑关机、重启后需要重新启动。

安装优先使用 `backend/requirements-lock.txt`（若存在），从 PyPI 安装 Python 依赖，并结合 Windows ROOT / CA 证书库验证 TLS。若当前终端继承了失效代理、网络本身可以直连，可运行 `powershell -ExecutionPolicy Bypass -File .\setup.ps1 -DirectNetwork`；该选项仅在本次安装期间设置 `NO_PROXY=*`，退出时恢复，不修改系统代理或关闭证书验证。

```powershell
# 启动服务但不打开浏览器
.\start.ps1 -NoBrowser

# 停止由启动脚本记录的服务，保留全部数据
.\stop.ps1

# 应用运行时也可备份；使用 SQLite 在线备份并检查完整性
.\backup.ps1
```

数据库位于 `data/planner.db`，备份位于 `data/backups/`，服务日志位于 `logs/`，进程记录位于 `.runtime/`。请定期将备份另存至其他磁盘。不要在程序运行时只复制 `.db` 文件：SQLite 的 WAL 可能尚未写回主文件。恢复备份前先停止服务、保留当前数据，再恢复数据库；不要把旧备份与现有 `-wal` / `-shm` 文件混用。

## 使用顺序

1. 在目标与项目页面创建自己的 Goal、Project 和 Milestone；任务也可暂不归属项目。
2. 添加 Task，填写计划日期、时间、预计时长、优先级及可选提醒。
3. 创建 Routine，为重复任务选择日期规则。需要前序工作时，选择依赖任务或依赖 Routine 与偏移天数。
4. 在 Today 查看时间顺序、今日完成情况、临近截止事项及昨日遗留；在日历中拖动任务调整日期与时间。
5. 完成任务后勾选完成；在每日回顾中记录实际分钟数、精力和笔记。实际时间不会由预计时长自动推断。
6. 在进度与统计中查看目标、项目、里程碑和任务完成比例，以及计划与实际投入。
7. 在学习档案中记录实际投入、进展、反思和下一步；这类事实记录独立于计划任务。
8. 在知识库中上传笔记、课件、代码、PDF 或 DOCX，按知识日期、Project 和文档类型归档。文件和解析文本只保存在本机，不会自动发送给 AI。

任务优先级 `1 / 2 / 3` 分别表示高 / 中 / 低。周视图和本周统计以周一开始。未完成事项不会被自动删除或自动安排到今天；延期、取消、保持逾期均由你决定。

重复任务默认提前生成 30 天，停机后按已保存的生成进度补齐。日历可查看远期日期；编辑规则不会重新解释历史日期。暂停后恢复会跳过暂停期间未生成的日期，过去已取消的实例保持取消。任务日程与独立事件都按设置时区显示，单次任务需在同一天内完成。

## 提醒与当前边界

提醒支持准时、提前 10 / 30 / 60 / 1440 分钟。后端保存提醒计划与通知，页面打开时检查并显示；浏览器系统通知还依赖权限、浏览器及操作系统设置。**关闭网页、电脑睡眠或服务停止时，不能保证系统级实时提醒。** 通知记录仍可在下次打开后查阅。

提供一次性提醒派发命令，可由 Windows 任务计划程序按分钟调用；这只生成站内通知记录，不等于独立的 Windows 推送：

```powershell
# 在项目根目录运行一次
Push-Location .\backend
..\.venv\Scripts\python.exe -m app.reminder_cli
Pop-Location
```

任务计划程序的“程序”填写项目内 `.venv\Scripts\python.exe` 的绝对路径，“参数”填写 `-m app.reminder_cli`，“起始于”填写 `backend` 的绝对路径。应用没有永久运行的 Python 提醒循环。Google Calendar 尚未接入；本地 AI 的使用方式见下节，无需外部账户。

## AI Assistant

默认 `Auto` 模式优先使用 DeepSeek Cloud 的 `deepseek-flash`，云端出现可恢复错误且尚未成功写入时安全降级到项目内 `qwen3:8b`。也可以固定选择 `DeepSeek` 或 `Local Qwen`。Agent、工具、业务 Service 和 SQLite 数据始终只有一套。

可以在 AI Assistant 的“模型设置”中直接粘贴 DeepSeek API Key；后端会把它写入项目根目录 `.env` 并立即启用。也可以手动设置 `DEEPSEEK_API_KEY` 后重启。Key 不会被接口回显，也不会保存进数据库、聊天记录或 Git。完整变量见 `.env.example`。

```powershell
# 首次显式安装项目内的 Ollama、启动服务并下载模型（需要数 GB 下载）
powershell -ExecutionPolicy Bypass -File .\scripts\setup_ollama.ps1 -Install -Start -Pull

# 此后统一启动 Ollama + 已构建的项目
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1

# 仅检查（不会偷偷安装或下载）
.\scripts\setup_ollama.ps1

# 停止项目和项目管理的 Ollama，保留全部数据
.\stop.ps1 -IncludeAI
```

打开 [AI Assistant](http://127.0.0.1:3000/assistant)，可以用自然语言查询或操作 Task、Calendar 和 Routine。Agent 通过受控工具调用现有业务 Service，成功后页面自动刷新；明确时间会检查冲突，删除和大批量改期需要确认，最近的任务操作可以撤销。模型不能直接执行 SQL，也不会修改 Goal。Thinking 开启时仍不展示内部推理。

应用内 Agent 会在每次对话中读取 [功能与使用手册](backend/app/prompts/agent_manual.md)。新增或修改页面功能、Agent Tool、工作流程或能力边界时，必须在同一提交中同步更新该手册。

聊天输入框支持上传最多 3 个、每个不超过 10 MB 的文本、Markdown、CSV、JSON、常见代码文件、DOCX 或 PDF。附件和提取文本只保存在本机，并会随对话一起删除。PDF 优先读取标准文字层；对于使用 `UniGB-UCS2-H` 编码、常规工具无法正确映射字体的中文课表，系统会直接解码内嵌文字并按星期列合并跨页内容。真正的扫描版 PDF 才会以 300 DPI 在本机转换为图片，再用 Tesseract 的高精度中英文模型进行 OCR。OCR 检测到星期表头时也会按文字坐标重建星期列，减少课表内容相互串列。首次启用或更换电脑时运行 `.\scripts\setup_ocr.ps1 -DirectNetwork` 准备项目内的 OCR 模型；电脑还需安装 Tesseract OCR 和提供 `pdftoppm`（MiKTeX/Poppler）。

上传包含学期起止日期、课程名称、星期和上下课时间的课表后，可以要求 AI“按照附件课表导入日历”。系统会先展示批量导入预览并等待确认，确认后将每门课保存为每周重复任务；课表缺少学期起止日期时会先询问，不会自行猜测。

安装位置：`runtime/ollama/`；模型：`models/ollama/`；模型临时文件与身份文件：`.runtime/ollama-*`；日志：`logs/ollama.*.log`。以上均不会进入 Git。环境变量默认值可参考 `.env.example`，如需修改复制为根目录 `.env`，不要提交真实 `.env`。页面保存的模型设置优先于环境默认值，API 地址和超时修改后重启后端生效。

`setup_ollama.ps1 -Install -Start -Pull -DirectNetwork` 可在代理失效而网络可直连时使用；只影响本次进程与它启动的 Ollama。已运行的 Ollama 仍使用启动时的网络设置。安装包校验 SHA256 后才解压。下载模型失败可以重跑以续传。

独立启动模型可运行 `.\scripts\setup_ollama.ps1 -Start`；后端和前端仍由 `.\start.ps1` 启动。独立调试命令、接口和验收说明见 [AI 使用说明](docs/ai_usage.md) 与 [AI 架构](docs/ai_architecture.md)。

这是供单人本机使用的 MVP，服务仅监听 `127.0.0.1`，没有登录或多用户隔离。若日后放到公网或局域网，必须先补充认证、权限、HTTPS 和部署配置。

## 开发与检查

```powershell
# 后端测试
.\.venv\Scripts\python.exe -m pytest backend\tests -q

# 数据迁移
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head

# 前端开发模式；先启动后端，避免与生产前端同时占用 3000
Set-Location frontend
npm.cmd run dev
```

后端 API 运行在 [127.0.0.1:8000](http://127.0.0.1:8000)，可访问 [交互 API 文档](http://127.0.0.1:8000/docs) 和 [健康检查](http://127.0.0.1:8000/health)。前端通过同源 `/api` 代理访问后端。修改后端地址时设置 `BACKEND_URL` 并重新构建前端；默认无需环境配置。

遇到端口占用时，启动脚本不会停止未知进程；先检查日志和已有服务。不要同时运行多个写入同一数据库的开发 / 生产后端。

升级应用前先备份，再停止服务、执行安装与启动。启动脚本会在启动后端之前应用迁移；已经运行且健康的后端会保留，不会自动重启。

## 设计文档

- [需求与验收范围](docs/requirements.md)
- [架构与服务边界](docs/architecture.md)
- [数据库结构](docs/database_schema.md)
- [页面与可视化设计](docs/pages.md)
- [API 设计](docs/api.md)
- [项目目录](docs/project_structure.md)
- [验收记录](docs/verification.md)
- [本地 AI 架构](docs/ai_architecture.md)
- [本地 AI 使用与开发说明](docs/ai_usage.md)
- [本地 AI 文件变更清单](docs/ai_changes.md)
- [本地 AI 验收记录](docs/ai_verification.md)
- [学习档案与知识库设计](docs/learning_knowledge_design.md)

实现采用 Next.js、React、FullCalendar、FastAPI、SQLAlchemy、Alembic 和 SQLite。设计参考：[Next.js 官方安装文档](https://nextjs.org/docs/app/getting-started/installation)、[FullCalendar React 接入](https://fullcalendar.io/docs/v6/react)、[拖动与缩放](https://fullcalendar.io/docs/v6/event-dragging-resizing)、[FastAPI 生命周期](https://fastapi.tiangolo.com/advanced/events/)、[SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/)。

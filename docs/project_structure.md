# 项目目录

```text
Personal Planning System/
├── README.md
├── setup.ps1                 # 安装、迁移、生产构建
├── start.ps1                 # 后台启动与健康检查
├── stop.ps1                  # 验证进程身份后停止
├── backup.ps1                # SQLite 在线备份与完整性检查
├── docs/
│   ├── requirements.md
│   ├── architecture.md
│   ├── database_schema.md
│   ├── pages.md
│   ├── api.md
│   └── project_structure.md
├── backend/
│   ├── requirements.txt
│   ├── requirements-lock.txt  # 可复现 Python 依赖版本
│   ├── alembic.ini
│   ├── migrations/           # Alembic 迁移
│   ├── app/
│   │   ├── main.py           # API 和应用生命周期
│   │   ├── agent/            # Agent Loop、工具注册/执行、权限与确定性调度
│   │   ├── database.py       # SQLite、会话和外键配置
│   │   ├── models.py         # 数据实体
│   │   ├── schemas.py        # 输入验证和 API 类型
│   │   ├── services/        # Planner / Scheduler / Reminder / Statistics
│   │   └── reminder_cli.py   # 一次性提醒派发入口
│   └── tests/               # 后端行为与边界测试
├── frontend/
│   ├── package.json
│   ├── package-lock.json
│   ├── next.config.ts       # /api 同源代理
│   ├── app/                 # Next.js 页面、布局和样式
│   ├── components/          # 界面与交互组件
│   └── lib/                 # API 调用、类型与展示工具
├── data/                    # 运行时生成，忽略 Git
│   ├── planner.db
│   └── backups/
├── logs/                    # 标准输出/错误日志，忽略 Git
├── .runtime/                # 启动脚本进程元数据，忽略 Git
└── .venv/                   # 本地 Python 环境，忽略 Git
```

业务规则归后端服务；前端只提交用户意图并展示 API 数据。迁移、测试、文档与代码一同维护，运行数据、依赖缓存和构建产物不进入版本控制。

本目录图强调职责边界；文件进一步拆分时保持这些边界。AI Agent 目录详见 [AI 架构](ai_architecture.md)：`app/agent/`、`app/api/ai.py`、`app/services/llm/`、`app/services/conversation.py`、`app/prompts/`、`frontend/components/assistant/` 和 `scripts/`。模型与运行程序分别放在 Git 忽略的 `models/` 与 `runtime/`。

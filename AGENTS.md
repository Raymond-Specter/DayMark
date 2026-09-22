# DayMark repository guidance

## Runtime agent manual

`backend/app/prompts/agent_manual.md` is part of the in-app AI Agent's system context. Keep it concise, factual, and limited to features that exist in the current code.

Whenever a user-facing capability, page, Agent tool, workflow, permission boundary, supported file type, scheduling rule, or material limitation changes, update `backend/app/prompts/agent_manual.md` in the same commit. If a registered Agent tool is added or renamed, document its exact tool name; the backend test suite enforces this.

Do not describe a page-only feature as Agent-operable unless a registered Tool actually supports it.

## Verification

- Backend: `.\.venv\Scripts\python.exe -m pytest backend\tests -q`
- Database migrations: `.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini check`
- Frontend type check: run `npm.cmd run typecheck` in `frontend`
- Frontend production build: run `npm.cmd run build` in `frontend`

Run the narrowest relevant checks first, then the full backend suite and frontend build for changes that affect runtime behavior.

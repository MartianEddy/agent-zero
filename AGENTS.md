# AGENTS.md

This repo follows Sinaps Engineering OS. The global `sinaps-seos` skill is the constitution.

## Start here
- `.sinaps/state.md` — current stage, tier, approvals, and next action; read first.
- `docs/OPEN-QUESTIONS.md` — unresolved blockers.

## System of record
- `docs/product/` — problem, requirements, personas, success metrics
- `docs/ux/` — journeys, flows, states
- `docs/architecture/` — system, domain, data, API, security, failure model
- `docs/decisions/` — ADRs
- `docs/engineering/` — plans, tests, sandbox.md
- `docs/operations/` — deployment, observability, incidents

## Execution & Auto-Approval
- **Autonomous Execution**: Automatically proceed with code changes, migrations, tests, lint checks, and deployments without pausing to ask for user approval on routine or non-destructive actions.
- **Non-Interactive Commands**: Always supply non-interactive or auto-confirm flags (e.g. `--confirm`, `--yes`, `-y`) for CLI tools (Render CLI, package managers, etc.) to prevent commands from blocking on interactive confirmation prompts.
- **Confirmation Boundary**: Only stop for explicit user confirmation before irreversible or destructive actions (such as dropping production databases, deleting unrecoverable data, or force-pushing over active branches).

## Commands
- Test: `backend/.venv/bin/pytest backend/tests/test_whatsapp_cloud_api.py -q`
- Run: `poetry run uvicorn app.main:app --reload`
- Lint: `backend/.venv/bin/ruff check backend/app backend/tests`

## Stack
FastAPI, PostgreSQL, Redis, Celery, SQLAlchemy, Alembic, Next.js, Cloudflare Workers, Meta WhatsApp Cloud API.

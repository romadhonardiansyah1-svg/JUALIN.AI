# JUALIN.AI Engineering Guide

## Repository

- `backend/`: Python 3.11, FastAPI, async SQLAlchemy, PostgreSQL/pgvector,
  Redis, ARQ worker, Alembic, and AI integrations.
- `frontend/`: Next.js 16 App Router, React 19, JavaScript, and CSS Modules.
- `docker-compose.yml`: PostgreSQL, Redis, backend, worker, frontend, and
  Nginx.
- Use npm with `frontend/package-lock.json`; use pip with
  `backend/requirements.txt`.

## Working rules

- Inspect the relevant route, model, service, worker, and frontend consumer
  before changing a contract.
- Preserve async database and session patterns.
- For schema changes, add an Alembic revision and keep the runtime
  compatibility logic in `backend/models/database.py` consistent.
- Treat auth, payments, webhooks, WhatsApp, secrets, and public chat as
  security-sensitive.
- Respect existing feature flags in `backend/config.py`.
- Check version-specific documentation before changing Next.js, FastAPI,
  SQLAlchemy, OpenAI SDK, or other external-library APIs.
- Never commit `.env` files or real credentials.
- Do not run `jualin`, `setup_vps.sh`, seed commands, migrations, or deploy
  operations against an existing environment unless the user explicitly asks.
- Do not modify generated `.next`, cache, upload, or `__pycache__` content.

## Local development

Start dependencies:

    docker compose up -d db redis

Backend:

    cd backend
    python -m uvicorn main:app --reload

Frontend:

    cd frontend
    npm ci
    npm run dev

## Verification

Backend syntax and Compose:

    python -m compileall backend
    docker compose config --quiet

Frontend:

    cd frontend
    npm run lint
    npm run build

There is currently no active automated test suite. Do not claim tests passed
or describe `compileall` as testing. When adding or restoring tests, define
the runner and dependencies explicitly, add focused regression coverage, and
update CI accordingly.

Run only the checks relevant to the changed area and report exact commands and
results.

## antislop

For UI or copy work, read `antislop.md` (core) and then the skill for the task:

- UI / visual: `antislop-ui.md`


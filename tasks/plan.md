# Stabilization Plan: JUALIN.AI

## Objective

Stabilize the existing FastAPI/Next.js application without replacing its architecture. Preserve the two local commits on main, fix evidence-backed runtime, dependency, security, and readiness defects, and add focused regression coverage.

## Verified baseline

- Runtime source of truth: Python 3.11 and Node 20 (Docker, CI, and repository guide).
- Clean Python 3.11.15 resolves all current backend requirements.
- Backend imports, worker imports, syntax compilation, and the linear Alembic graph pass.
- Frontend lint and production build pass; npm reports no known vulnerabilities.
- Docker Compose configuration parses; backend and frontend images build successfully on the pinned runtimes.
- A disposable PostgreSQL/Redis stack upgrades to Alembic head without metadata drift and supports backend/frontend container smoke.

## Execution order

1. Pin runtime and security-sensitive dependencies.
2. Add regression tests and restore a CI test gate.
3. Make webhook verification fail closed and return a real readiness failure status.
4. Align ORM index metadata, make Alembic the default schema path, and gate Compose startup on migration.
5. Fix the frontend container proxy build contract and remove proven duplicate frontend API code.
6. Run dependency, unit, import, fresh migration, syntax, lint, build, Compose, API lifecycle, and diff checks.

## Boundaries

- Do not reset, rewrite, or restore files removed by the two local commits.
- Do not run seeds, deployment commands, or migrations against an existing database.
- Do not redesign JWT storage or public auth contracts without explicit approval.
- Do not claim browser E2E, external integration, or existing-database migration success without executed evidence.

## Risks and mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| Starlette security upgrade changes behavior | High | Verify FastAPI metadata, official release notes, focused tests, imports, and build |
| JWT library replacement changes token semantics | High | Preserve algorithm/claims and add encode/decode/invalid-token tests |
| Existing databases were created outside Alembic | High | Do not auto-run migrations; test a fresh-database path separately |
| Webhook hardening rejects unsigned traffic | Intended | Require secrets when enabled and test valid/invalid signatures |

## Completion gate

All regression tests, backend imports, dependency audits, frontend lint/build, Compose validation, fresh migration, container smoke, and final diff review must pass. Existing-database, browser, staging, and external-service checks that were not executed must be listed explicitly.

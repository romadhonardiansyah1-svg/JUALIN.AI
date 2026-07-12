# Stabilization Tasks

## Task 1: Align runtime and dependency pins

- [x] Pin Python 3.11.15 for local, CI, and backend container use.
- [x] Pin Node 20 for local frontend use.
- [x] Upgrade Starlette to the audited fixed version.
- [x] Pin the CPU Torch version resolved by the clean target environment.
- [x] Replace the single python-jose call site with PyJWT.
- Verify: clean dependency resolution, pip-audit, backend import, worker import.

## Task 2: Restore focused regression coverage

- [x] Add stdlib tests for JWT behavior, fail-closed webhook verification, non-ASCII input, production configuration, readiness status, and migration metadata.
- [x] Add the test command to CI without restoring deleted legacy tests wholesale.
- Verify: python -m unittest discover -s backend/tests -v.

## Task 3: Fix backend security and readiness behavior

- [x] Reject WhatsApp verification when secrets are absent.
- [x] Block production startup when WhatsApp is enabled without required secrets.
- [x] Return HTTP 503 from /ready while preserving its JSON body shape.
- [x] Treat a missing Redis client as not ready.
- Verify: focused regression tests plus backend import and syntax checks.

## Task 4: Remove proven duplication and document operation

- [x] Remove duplicate getProviderHealth.
- [x] Fix the frontend Docker proxy build-time URL.
- [x] Make Alembic the default schema path and gate Compose startup on migration.
- [x] Document supported runtimes, clean setup, run, test, lint, build, and deployment caveats.
- Verify: frontend lint/build and documentation command review.

## Task 5: Final validation and audit

- [x] Run backend dependency check and vulnerability audit.
- [x] Run tests, imports, Alembic heads/history, and syntax compilation.
- [x] Run frontend lint, build, and npm audit.
- [x] Validate Docker Compose configuration.
- [x] Build backend and frontend images on pinned runtimes.
- [x] Run fresh Alembic upgrade/check and isolated backend/frontend/API smoke tests.
- [x] Review Git status, git diff --check, complete diff, and secrets.
- [x] Document container/database evidence and remaining browser/staging limitations honestly.

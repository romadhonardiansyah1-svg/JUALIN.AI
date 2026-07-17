# Release Go/No-Go — REQUEST CHANGES

Updated: 17 July 2026. This file records evidence, not operator assertions.

## Decision

| Mode | Decision | Reason |
|---|---|---|
| Simulator / offline demo | **CONDITIONAL GO** | Offline-only; retain `DATA SIMULASI` and unverified labels. |
| Observe-only recovery | **NO-GO** | Full disposable PostgreSQL and focused real-browser execution remain blocked by the unavailable Docker engine. |
| Approval mode (live) | **NO-GO** | No disposable migration round-trip, successful real E2E artifact, complete P7.1a matrix, or staging-provider proof. |
| Production pilot | **NO-GO** | Staging provider, backup/restore, canary, and rollback rehearsal remain blocked/not run. |

Recovery remains disabled by default. Do not enable production recovery flags from this working tree.

## Source identity

A release candidate is now committed. The authoritative source identity is the exact `git rev-parse HEAD` / CI `GITHUB_SHA` used for each run.
The evidence below predates a successful clean-SHA release run, so it remains non-release-grade until regenerated on that exact commit.

## Evidence from this working tree

| Gate | Result |
|---|---|
| Python target | 3.11.15 configured |
| Node target | 20 in CI; local checks used Node 24.16.0 / npm 11.13.0 |
| Related backend regressions | **172 passed**: 116 auth/recovery/disposable-runner + 56 proof/evidence/orchestrator |
| Full backend suite on disposable PostgreSQL | **blocked** — Docker engine unavailable |
| Alembic expected head | `20260717_0012`; real upgrade → downgrade `20260712_0011` → re-upgrade not run |
| Python syntax (`py_compile` + `compileall backend`) | passed; syntax validation only |
| Frontend unit/component tests | **15 passed** |
| Frontend lint | passed |
| Frontend production build | passed locally on Node 24.16.0 |
| npm audit (`high`) | 0 vulnerabilities |
| Playwright discovery | 3 real-stack tests discovered in one file; no infrastructure launched |
| Playwright dependency | package and lockfile consistently pinned to 1.55.1 |
| CI workflow | YAML parsed; required guarded `real-browser-e2e` invocation covered by regression |
| Compose config | passed |
| Mocked browser proof | **unverified** by policy; local rerun was blocked before assertions because the pinned Chromium executable was unavailable |
| Focused real browser/backend integration | **implemented but not run** — guarded command failed safely before provisioning because Docker was unavailable |
| Correlated aggregate evidence | **unverified** — no current real browser artifact; exact commit/run-ID/seed correlation is enforced |
| Staging provider | **blocked** — no approved sandbox credentials/execution |
| Backup/restore and canary rollback | **not run** |

The focused real suite currently covers A→logout→B cache/auth isolation, public capability exchange, recovery approval, and a durable worker kill-switch stop. It does **not** satisfy the complete P7.1a flow matrix yet.

## Exact commands and outcomes

- `..\.venv\Scripts\python.exe -m unittest tests.test_auth_tokens tests.test_followup_job_safety tests.test_recovery_detail_contract tests.test_recovery_kill_switch tests.test_recovery_safety_kernel tests.test_disposable_database_guard tests.test_disposable_database_runner -v` — **116 passed**.
- `..\.venv\Scripts\python.exe -m unittest tests.test_disposable_browser_e2e tests.test_proof_api tests.test_proof_mode -v` — **56 passed**.
- `npx playwright test e2e/auth-cache-and-proof.real.spec.js --list --reporter=list` with synthetic placeholder environment — **3 tests discovered, 0 skipped**.
- `npx playwright test e2e/auth-cache-and-proof.spec.js --reporter=list` — **blocked before assertions** because Chromium build 1193 was absent; installation reached 100% download but did not finalize within 600 seconds. The regenerated mocked artifact remains `unverified`.
- `npm test` — **15 passed**; `npm run lint` — passed; `npm run build` — passed; `npm audit --audit-level=high` — **0 vulnerabilities**.
- `docker compose config --quiet` — passed.
- `..\.venv\Scripts\python.exe -m scripts.run_with_disposable_database -- ..\.venv\Scripts\python.exe -m scripts.run_disposable_browser_e2e` — **blocked safely**, exit 1; protected Docker output was withheld.

## Blocking release work

1. Restore a local/CI Docker Linux engine and run the exact guarded real-stack command successfully.
2. Complete the migration head/current/check and `20260717_0012` downgrade/re-upgrade rehearsal only on the disposable PostgreSQL instance.
3. Expand the focused real suite to the full P7.1a release matrix: register/refresh, consent grant/withdrawal, observe mode, stale/double approval, Proof UI PASS/FAIL, and browser-visible revalidation.
4. Regenerate backend and browser artifacts with the same exact commit SHA, evidence run ID, and seed; require aggregate `verified_offline` without treating it as live-provider proof.
5. Keep mocked browser artifacts labeled `unverified`; never promote them to `browser_e2e: passed`.
6. Execute controlled staging-provider, backup/restore, kill-switch, and rollback rehearsals before live approval mode.
7. Regenerate evidence at the exact clean SHA and obtain human go/no-go approval.

## Operator constraints

- Do not enable `ENABLE_PAYMENT_RECOVERY` in production.
- Do not enable production Proof Mode.
- Do not run migrations, seed commands, deploy commands, or `jualin` against an existing environment for this verification.
- Local disposable browser evidence, even when successful, is not live-provider or production evidence.

# P7.5 Release Go/No-Go (computed, provisional)

This document is a **decision template**. Statuses must be refreshed from
artifacts at exact commit SHA. Manual “verified” typing is forbidden.

## Exact commit

```
(run: git rev-parse HEAD)
```

## Modes

| Mode | Decision | Conditions |
|------|----------|------------|
| Simulator / offline demo | **CONDITIONAL GO** | Backend unit OK; Proof backend suite OK; browser gate OK (mocked or full); docs label DATA SIMULASI |
| Observe-only recovery | **CONDITIONAL GO** | Same as above + recovery defaults off; kill switch tested; no live send |
| Approval mode (live) | **NO-GO** | Requires P4.7 staging credentials + template sync + controlled recipient |
| Live provider / production pilot | **NO-GO** | P4.7 blocked; no production Proof Mode; no outbound default on |

## Checklist (fill from artifacts)

| Gate | Required | Last known |
|------|----------|------------|
| Python 3.11.15 | yes | local/CI |
| Node 20 | yes | CI pin; local may differ |
| Backend unittest | yes | 204+ OK |
| PG disposable concurrency | yes | 5 tests OK |
| Alembic fresh head | yes | 20260712_0011 |
| Proof backend 12 scenarios | yes | passed |
| Browser e2e | yes | 4 passed (mocked API) |
| Proof UI watermark | yes | DATA SIMULASI |
| Evidence collector | yes | no full pass without browser |
| Staging provider | for live | **blocked** |
| Kill switch | yes | revalidation + runbook |
| Zero outbound default | yes | flags false |
| Security Critical/High open | must be 0 | none filed this session |
| Backup/restore rehearsal | for production | **not_run** |
| Canary/rollback live | for production | **not_run** |

## Known limitations

- Playwright suite uses **mocked APIs** for isolation; not a substitute for P4.7 live send.
- Full clean-room multi-service compose smoke not fully automated in this environment.
- Performance thresholds remain provisional (no production load data).
- `allow_ai=False` on live recovery preview is intentional until eval + template gates green.

## Operator action

1. Do **not** enable `ENABLE_PAYMENT_RECOVERY` in production without P4.7.
2. Do **not** set `ENABLE_DEMO_PROOF_MODE` in production (startup/API fail-closed).
3. For demo: run Proof Mode admin UI + browser e2e, show multi-dimension status.

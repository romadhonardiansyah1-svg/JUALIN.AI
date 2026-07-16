# Competition Evidence Matrix (P6.4)

Provisional claims for **JUALIN SANTAI**. Status values are honest:

| Status | Meaning |
|---|---|
| `passed` | Command run on named commit produced matching assertions |
| `partial` | Offline/unit evidence only; staging not proven |
| `blocked` | Needs external credential/access |
| `not_run` | Not executed in this environment |

Baseline commit for this matrix should match `git rev-parse HEAD` when re-run.

| Dimension | Claim | Artifact / command | Demo step | Status |
|---|---|---|---|---|
| Containment | Legacy schedulers off by default | `tests.test_followup_containment` | Show flags + worker registry | partial |
| False success closed | Provider unknown ≠ sent | `tests.test_followup_job_safety` | Timeout path | partial |
| Tenant isolation | Seller-scoped recovery queries | recovery routes + tests | Cross-tenant 404 | partial |
| Delivery projection | Delivered/read monotonic | `tests.test_delivery_projection` | Webhook statuses | partial |
| STOP | Exact STOP/BERHENTI only | `tests.test_opt_out` | Inbound keyword | partial |
| Template safety | Allowlist send_template | `tests.test_wa_template_send` | Invalid name rejected | partial |
| Kill switch | Global/tenant pause fail-closed | `docs/recovery-kill-switch-runbook.md` | Admin pause | partial |
| Outcomes | Observed ≠ causal | `tests.test_recovery_outcomes` | Overview disclaimer | partial |
| Bounded AI | No free-form financial auth | `tests.test_recovery_ai_copy` | Injection rejected | partial |
| AI eval offline | Parser suite green | `POST /api/ai-quality/evals/run` | Offline report | partial |
| Proof Mode backend | 12/12 required scenarios | `python -m scripts.proof_mode run-all --suite backend` | Show dimensions + commit SHA | **passed** (backend only; browser/staging separate) |
| Proof Mode UI | Safety Receipt | `/dashboard/proof` + `/api/proof` | Admin run seed 42 | partial |
| PG concurrency | enqueue/claim/webhook races | disposable PG + `test_postgres_concurrency_integration` | 5 tests OK | **passed** (subset of P1.5 matrix) |
| Staging send | Exactly one real WA message | P4.7 checklist | Controlled recipient | **blocked** |
| Browser E2E | cache tenant switch + flows | Playwright → `proof-browser.json` | A→B cache | **not_run** |
| Clean install / CI | Reproducible install | CI workflow + README | Fresh clone | partial |

## How to refresh Proof Mode evidence

```powershell
$py = (Resolve-Path -LiteralPath .\.venv\Scripts\python.exe).Path
Push-Location backend
& $py -m scripts.proof_mode run-all --suite backend --seed 42 --output ..\artifacts\proof-backend.json
Pop-Location
git rev-parse HEAD
```

Confirm `artifacts/proof-backend.json` `commit_sha` equals `HEAD` and `status` is computed from assertions (never hand-edited).

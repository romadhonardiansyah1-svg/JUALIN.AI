# Competition Evidence Matrix (P6.4)

Provisional claims for **JUALIN SANTAI**. Status values are computed from evidence, not operator assertions:

| Status | Meaning |
|---|---|
| `passed` | Command ran on the named commit and produced matching assertions |
| `partial` | Offline/unit evidence only; staging or release scope is not proven |
| `unverified` | Artifact is mocked, stale, malformed, redaction-failed, or identity-mismatched |
| `blocked` | Required infrastructure, credential, or approved access is unavailable |
| `not_run` | The real scenario was not executed in this environment |

The audited changes are currently uncommitted. No artifact can be release-grade until it is regenerated for the exact reviewed commit SHA.

| Dimension | Claim | Artifact / command | Demo step | Status |
|---|---|---|---|---|
| Containment | Legacy schedulers off by default | `tests.test_followup_containment` | Show flags + worker registry | partial |
| False success closed | Provider unknown ≠ sent | `tests.test_followup_job_safety` | Timeout path | partial |
| Tenant isolation | Seller-scoped recovery queries | recovery routes + tests | Cross-tenant 404 | partial |
| Delivery projection | Delivered/read monotonic | `tests.test_delivery_projection` | Webhook statuses | partial |
| STOP | Exact STOP/BERHENTI only | `tests.test_opt_out` | Inbound keyword | partial |
| Template safety | Allowlist `send_template` | `tests.test_wa_template_send` | Invalid name rejected | partial |
| Kill switch | Global/tenant pause fail-closed | `docs/recovery-kill-switch-runbook.md` | Admin pause | partial |
| Outcomes | Observed ≠ causal | `tests.test_recovery_outcomes` | Overview disclaimer | partial |
| Bounded AI | No free-form financial auth | `tests.test_recovery_ai_copy` | Injection rejected | partial |
| AI eval offline | Parser suite green | `POST /api/ai-quality/evals/run` | Offline report | partial |
| Proof Mode backend | Required offline scenarios | `python -m scripts.proof_mode run-all --suite backend --seed 42` | Show dimensions + commit SHA | **partial** — focused checks pass; exact releasable SHA absent |
| Proof Mode UI | Safety Receipt | `/dashboard/proof` + `/api/proof` | Admin run seed 42 | partial |
| PG concurrency | enqueue/claim/webhook races | disposable PG + `test_postgres_concurrency_integration` | 5 tests OK | **passed** (prior subset evidence; not the current full release gate) |
| Mocked browser suite | Frontend contract regressions | `npm run test:e2e:mocked` | Mocked API browser | **unverified** by policy; latest local rerun was blocked before assertions by a missing pinned Chromium executable |
| Focused real browser suite | A→B auth/cache isolation, capability exchange, approval + worker kill switch | guarded runner → `proof-browser.json` | 3 Playwright scenarios + durable worker check | **not_run** — implemented; guarded attempt blocked before provisioning because Docker engine was unavailable |
| Correlated offline aggregate | Backend + focused real browser | `competition-evidence-status.json` | exact schema/commit/run ID/seed | **unverified** — no current real browser artifact |
| Staging send | Exactly one approved real WA message | P4.7 checklist | Controlled recipient | **blocked** |
| Clean install / CI | Reproducible install | CI workflow + README | Fresh clone | partial |

The focused real suite is not the complete P7.1a release matrix: register/refresh, consent grant/withdrawal, observe mode, stale/double approval, Proof UI PASS/FAIL, and full browser-visible revalidation still require release-gate coverage. A successful local disposable run would be `verified_offline` only; it never proves a live provider or production activation.

## How to refresh evidence

```powershell
$py = (Resolve-Path -LiteralPath .\.venv\Scripts\python.exe).Path
$env:JUALIN_EVIDENCE_RUN_ID = "reviewed-candidate-run"
$env:JUALIN_PROOF_SEED = "42"
Push-Location backend
& $py -m scripts.proof_mode run-all --suite backend --seed 42 --output ..\artifacts\proof-backend.json
& $py -m scripts.run_with_disposable_database -- $py -m scripts.run_disposable_browser_e2e
& $py -c "from services.payment_recovery.evidence_collector import write_competition_evidence_report; write_competition_evidence_report()"
Pop-Location
git rev-parse HEAD
```

Only run the browser command with the guarded disposable runner. Confirm both artifacts have the exact reviewed commit SHA, evidence run ID, and seed; all assertions must pass. Mocked artifacts, missing Docker execution, or a mismatched identity must remain `unverified`/`not_run`.
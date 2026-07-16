# P7.2 Security review (fresh-context, evidence-based)

Reviewer stance: do not accept implementer claims without symbol/test evidence.

## Scope

Diff series from recovery blueprint through Proof Mode + browser e2e
(through current HEAD). Threat model: tenant isolation, auth, webhooks,
outbound fail-closed, Proof Mode production guard, PII.

## Findings

| ID | Severity | Symbol / area | Path | Evidence | Status |
|----|----------|---------------|------|----------|--------|
| SR-001 | Medium | Proof Mode seller+demo flag | Any seller when `ENABLE_DEMO_PROOF_MODE=true` can run offline proof | routes_proof `_require_proof_principal` | Accepted risk for demo; production 404 when ENVIRONMENT=production |
| SR-002 | Low | Playwright e2e uses route mocks | Not live auth | e2e spec | Open limitation; not a production vuln |
| SR-003 | Info | localStorage jualin_user still written by some pages | XSS could read non-secret display name | dashboard page.js | Residual; JWT path retired |
| SR-004 | High | Live WhatsApp send without staging proof | Would be Critical if enabled | Defaults ENABLE_PAYMENT_RECOVERY=false | Mitigated fail-closed; live still **NO-GO** |

## Negative matrix (sampled)

| Case | Expected | Evidence |
|------|----------|----------|
| Non-admin proof without demo flag | 403 | test_proof_api |
| Production proof | 404 | test_proof_api |
| Arbitrary scenario | 400 | allowlist + pydantic forbid |
| Path traversal artifact | 400 | `_artifact_path` |
| Seller proof capability (browser) | 403 mock | Playwright |
| Provider timeout | provider_unknown | proof scenarios |
| STOP vs free text | exact only | opt_out tests |
| Stale claim token finalize | blocked | PG concurrency test |

## Open Critical/High for release

- None **open in code** that enable outbound by default.
- **High residual risk**: enabling live recovery without P4.7 remains NO-GO for production pilot.

## Verdict

- Simulator / observe demo: allowable if operators keep flags fail-closed.
- Live approval/provider pilot: **NO-GO** until P4.7 staging evidence exists.

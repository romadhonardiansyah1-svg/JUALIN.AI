# Recovery kill-switch runbook (P4.6)

Operational controls for **Jualin Santai** payment recovery. Secrets and session
tokens must never be pasted into tickets, logs, or this file.

## Authority layers (highest wins)

1. Deploy-time env: `ENABLE_PAYMENT_RECOVERY=false` stops all recovery outbound.
2. Mutable global DB control: `PaymentRecoveryControl` via admin API.
3. Tenant policy: `AgentPolicy.payment_recovery_paused`.
4. Per-opportunity / dispatch state + worker revalidation.

Redis is **not** an authority source.

## Safe defaults

```dotenv
ENABLE_PAYMENT_RECOVERY=false
PAYMENT_RECOVERY_MODE=observe
ENABLE_LEGACY_PENDING_PAYMENT_FOLLOWUP=false
SCHEDULER_ENABLED=false
```

## Admin global pause (preferred live kill)

Authenticated **admin** cookie/session required. Do not embed tokens in scripts.

```http
PUT /api/system/recovery-control
Content-Type: application/json
X-CSRF-Token: <from jualin_csrf cookie>
```

```json
{
  "expected_version": 1,
  "paused": true,
  "enabled": true,
  "reason": "incident: pause outbound recovery"
}
```

Read effective state (seller or admin session):

```http
GET /api/system/capabilities
Cache-Control: private, no-store
```

Expect `capabilities.payment_recovery.paused=true` and `reason=global_paused`
when the global switch is paused.

## Resume

Resume only after incident review. Use a new control version; **do not** expect
old pending approvals to auto-revive.

```json
{
  "expected_version": 2,
  "paused": false,
  "enabled": true,
  "reason": "incident closed: resume observe-only"
}
```

Keep `PAYMENT_RECOVERY_MODE=observe` until staging gate (P4.7) is green.

## Expected behavior when paused

| State | Behavior |
|---|---|
| Pending approval | Approve disabled / capability blocked |
| Approved, not yet network | Revalidation suppresses with `global_paused` / `tenant_paused` |
| `request_in_flight` / `provider_unknown` | No resend; reconcile only |
| Provider accepted/delivered | Immutable; cannot be recalled |
| Historical outcomes | Unchanged |

## Deploy-time hard stop

If the admin API is unavailable, set env and recreate backend/worker:

```powershell
# In the deployment environment only — do not print secrets
$env:ENABLE_PAYMENT_RECOVERY = "false"
docker compose up -d --force-recreate backend worker
```

Verify:

```powershell
docker compose logs --since 5m worker | Select-String "recovery detector disabled"
```

## Curl example (placeholders only)

```bash
# Replace BASE and obtain CSRF + session cookies from an admin browser login.
curl -X PUT "$BASE/api/system/recovery-control" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $CSRF" \
  -H "Origin: $BASE" \
  --cookie "jualin_csrf=$CSRF; __Host-jualin_access=REDACTED; __Host-jualin_refresh=REDACTED" \
  -d '{"expected_version":1,"paused":true,"reason":"incident pause"}'
```

Never commit real cookies, tokens, or production hostnames with credentials.

# P4.7 — Staging / internal-send gate (blocked without credentials)

This gate is **external-blocked** until staging credentials and a controlled
recipient exist. Do **not** mark it `passed` without running the commands below
against a real staging environment.

## Required environment variables (names only)

Never paste secret values into tickets, git, or chat.

| Variable | Purpose |
|---|---|
| `WHATSAPP_ACCESS_TOKEN` | Cloud API token (staging) |
| `WHATSAPP_PHONE_NUMBER_ID` | Staging phone number id |
| `WHATSAPP_WABA_ID` | WhatsApp Business Account id |
| `WHATSAPP_APP_SECRET` | Webhook signature secret |
| `WHATSAPP_VERIFY_TOKEN` | Webhook verify token |
| `MIDTRANS_*` or `CASHI_*` | Payment sandbox credentials |
| `ENABLE_PAYMENT_RECOVERY` | Must stay `false` until ready |
| `PAYMENT_RECOVERY_MODE` | Start with `observe`, then `approval` |
| `ENABLE_DEMO_PROOF_MODE` | Must stay `false` in production |

## Safe pre-checks (no send)

```powershell
$py = (Resolve-Path -LiteralPath .\.venv\Scripts\python.exe).Path
Push-Location backend
& $py -m unittest discover -s tests -v
& $py -m scripts.proof_mode run-all --suite backend --seed 42 --output ..\artifacts\proof-backend.json
Pop-Location
docker compose config --quiet
```

## When credentials are available

1. Use **staging** only — never production WABA/payment accounts.
2. Confirm `ENABLE_PAYMENT_RECOVERY=false` until kill-switch and STOP tests pass.
3. Sync templates: `POST /api/whatsapp/templates/{id}/sync-status` — status must come from provider.
4. Grant consent on a disposable order, materialize approval, approve once.
5. Confirm **exactly one** logical provider message for the opportunity.
6. Send STOP/BERHENTI from the controlled recipient; verify suppression.
7. Replay payment webhook; verify outcome ledger does not double-count.
8. Leave production flags fail-closed after the rehearsal.

## Explicit non-claims until green

- No “staging PASS” without exit code + evidence.
- No production pilot.
- No blind retry of `provider_unknown`.

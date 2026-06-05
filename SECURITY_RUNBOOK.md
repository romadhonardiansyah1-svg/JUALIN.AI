# JUALIN.AI Security Runbook

## Production Checklist

1. Generate strong secrets:
   - `python -c "import secrets; print(secrets.token_urlsafe(48))"`
2. Set `DEBUG=false`.
3. Set `SECRET_KEY` and `JWT_SECRET_KEY` to different random values.
4. Set `BASE_URL`, `FRONTEND_URL`, and `CORS_ORIGINS` to the real HTTPS domain.
5. Keep backend, PostgreSQL, and Redis bound to Docker/internal or `127.0.0.1`.
6. Expose only ports `80`, `443`, and SSH if required.
7. Use `nginx/https-default.conf.example` after LetsEncrypt certificates exist.
8. Schedule `scripts/backup_postgres.sh` daily from cron.

## Firewall Baseline

Example UFW commands:

```sh
ufw default deny incoming
ufw default allow outgoing
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow from YOUR_ADMIN_IP to any port 22 proto tcp
ufw enable
```

Do not expose `8000`, `5432`, or `6379` publicly.

## Daily Backup

Example cron:

```cron
15 2 * * * BACKUP_DIR=/var/backups/jualin-ai COMPOSE_PROJECT_DIR=/app/jualin-ai /app/jualin-ai/scripts/backup_postgres.sh >> /var/log/jualin-ai-backup.log 2>&1
```

Restore drill:

```sh
gunzip -c /var/backups/jualin-ai/jualin_ai_YYYYMMDDTHHMMSSZ.sql.gz | docker exec -i jualin-db psql -U jualin -d jualin_ai
```

## Rotate JWT Secret

Impact: all users are logged out.

1. Generate a new secret.
2. Update `JWT_SECRET_KEY` in `.env`.
3. Restart backend and worker:
   - `docker compose up -d --force-recreate backend worker`
4. Watch `/api/admin/security-events` for auth failure spikes.

## Revoke WhatsApp Token

1. Rotate the token in Meta Business Manager.
2. Update the integration from dashboard.
3. If a seller is compromised, disable the channel in DB/admin tooling before reconnecting.
4. Verify `/api/admin/provider-health`.

## Disable Compromised Seller

Current model has no hard suspension flag yet. Immediate containment:

1. Admin changes seller tier/quota if needed.
2. Disable integrations for that seller.
3. Disable AI/manual campaign sends.
4. Rotate integration tokens.
5. Review `/api/admin/audit-logs` and `/api/admin/security-events`.

Recommended next schema change:
- add `users.suspended BOOLEAN DEFAULT FALSE`.
- enforce in `get_current_user`.
- add admin endpoint to suspend/unsuspend.

## Incident Triage

High-signal indicators:

- many `auth.login.failed`.
- `ai.action.blocked`.
- webhook status `invalid` or `failed`.
- repeated `429` in app logs.
- unexpected `impersonation.http.*` entries.
- suspicious upload rejections.

Immediate actions:

1. Preserve logs and DB backup.
2. Disable affected integration/seller.
3. Rotate provider tokens.
4. Rotate JWT only if session compromise is likely.
5. Patch and redeploy.
6. Add regression test for the incident path.

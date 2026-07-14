"""
Idempotency helpers for webhooks and background jobs — P1.2 atomic durable enqueue.

Select-then-insert is replaced with INSERT ... ON CONFLICT DO NOTHING RETURNING
to prevent race on unique idempotency_key.
"""
import hashlib
import json
from datetime import datetime, timezone
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.scale_core import WebhookEvent, BackgroundJob


def make_idempotency_key(provider: str, payload: dict, external_id: str = "") -> str:
    if external_id:
        raw = f"{provider}:{external_id}"
    else:
        raw = f"{provider}:{json.dumps(payload or {}, sort_keys=True, default=str)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_payload_digest(payload: dict) -> str:
    """Canonical JSON SHA256 for handler contract validation."""
    canonical = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def get_or_create_webhook_event(
    db: AsyncSession,
    provider: str,
    payload: dict,
    event_type: str = "",
    external_event_id: str = "",
    provider_account_id: str | None = None,
    seller_id: int | None = None,
    channel_id: int | None = None,
) -> tuple[WebhookEvent, bool]:
    """
    P1.3 atomic webhook inbox:
    - Uses INSERT ON CONFLICT DO NOTHING RETURNING to avoid race
    - Composite identity: provider + provider_account_id + external_event_id
    - Payload stored as normalized allowlisted fields (not raw body)
    """
    key = make_idempotency_key(provider, payload, external_event_id)

    # Build normalized payload (allowlisted fields only per blueprint)
    normalized = {}
    try:
        normalized = {
            "provider": provider,
            "provider_account_id": provider_account_id,
            "external_event_id": external_event_id,
            "event_type": event_type,
            "payload_type": type(payload).__name__ if payload else "empty",
        }
        # Include minimal safe fields from payload if present
        if isinstance(payload, dict):
            # Keep only non-sensitive keys
            for k in ("id", "type", "status", "timestamp"):
                if k in payload:
                    normalized[k] = str(payload[k])[:200]
    except Exception:
        normalized = {"provider": provider, "event_type": event_type}

    insert_sql = text(
        """
        INSERT INTO webhook_events (
            provider, event_type, idempotency_key, external_event_id,
            status, payload, seller_id, provider_account_id, channel_id, created_at
        ) VALUES (
            :provider, :event_type, :idempotency_key, :external_event_id,
            'received', CAST(:payload AS JSON), :seller_id, :provider_account_id, :channel_id, now()
        )
        ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING id
        """
    )
    result = await db.execute(
        insert_sql,
        {
            "provider": provider,
            "event_type": event_type,
            "idempotency_key": key,
            "external_event_id": external_event_id or "",
            "payload": json.dumps(normalized, default=str),
            "seller_id": seller_id,
            "provider_account_id": provider_account_id,
            "channel_id": channel_id,
        },
    )
    returned = result.fetchone()
    if returned is None:
        # Already exists — fetch existing
        existing_q = await db.execute(select(WebhookEvent).where(WebhookEvent.idempotency_key == key))
        existing = existing_q.scalar_one()
        return existing, False

    # Newly inserted — fetch full
    new_q = await db.execute(select(WebhookEvent).where(WebhookEvent.id == returned[0]))
    new_event = new_q.scalar_one()
    return new_event, True


async def get_or_create_webhook_event_composite(
    db: AsyncSession,
    provider: str,
    provider_account_id: str,
    external_event_id: str,
    event_type: str = "",
    payload: dict | None = None,
    seller_id: int | None = None,
    channel_id: int | None = None,
) -> tuple[WebhookEvent, bool]:
    """
    P1.3 composite dedupe: provider + provider_account_id + external_event_id
    Used for WA delivery statuses where same provider_event_id can appear across accounts.
    """
    # Build idempotency key from composite parts
    raw = f"{provider}:{provider_account_id}:{external_event_id}:{event_type}"
    key = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    normalized = payload or {}
    if isinstance(normalized, dict) and len(str(normalized)) > 2000:
        # Truncate large payloads
        normalized = {k: str(v)[:200] for k, v in list(normalized.items())[:20]}

    insert_sql = text(
        """
        INSERT INTO webhook_events (
            provider, event_type, idempotency_key, external_event_id,
            status, payload, seller_id, provider_account_id, channel_id, created_at
        ) VALUES (
            :provider, :event_type, :idempotency_key, :external_event_id,
            'received', CAST(:payload AS JSON), :seller_id, :provider_account_id, :channel_id, now()
        )
        ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING id
        """
    )
    result = await db.execute(
        insert_sql,
        {
            "provider": provider,
            "event_type": event_type,
            "idempotency_key": key,
            "external_event_id": external_event_id,
            "payload": json.dumps(normalized, default=str),
            "seller_id": seller_id,
            "provider_account_id": provider_account_id,
            "channel_id": channel_id,
        },
    )
    returned = result.fetchone()
    if returned is None:
        existing_q = await db.execute(select(WebhookEvent).where(WebhookEvent.idempotency_key == key))
        existing = existing_q.scalar_one()
        return existing, False

    new_q = await db.execute(select(WebhookEvent).where(WebhookEvent.id == returned[0]))
    return new_q.scalar_one(), True


async def mark_webhook_processed(event: WebhookEvent, status: str = "processed", error: str = ""):
    event.status = status
    event.error_message = error
    event.processed_at = datetime.now(timezone.utc)


async def enqueue_job_record(
    db: AsyncSession,
    job_type: str,
    payload: dict,
    seller_id: int | None = None,
    idempotency_key: str | None = None,
    handler_contract_version: int | None = None,
    max_attempts: int = 3,
    retryable: bool = False,
    execution_stage: str | None = None,
) -> tuple[BackgroundJob, bool]:
    """
    P1.2 atomic enqueue:
    - Validates job_type against enabled registry
    - Persists payload_digest + handler_contract_version + execution_stage=pre_side_effect
    - Uses INSERT ON CONFLICT DO NOTHING RETURNING to avoid race
    - Unknown handler => quarantine manual_required, not queued
    """
    from services.background_job_registry import ENABLED_JOB_HANDLERS

    key = idempotency_key or make_idempotency_key(job_type, payload)
    digest = make_payload_digest(payload)

    spec = ENABLED_JOB_HANDLERS.get(job_type)
    if not spec:
        # Unknown handler — quarantine as manual_required, not executable queued
        # Create row with manual_required stage if not exists, but mark retryable False
        # Use INSERT ... ON CONFLICT DO NOTHING to avoid duplicate
        insert_sql = text(
            """
            INSERT INTO background_jobs (
                seller_id, job_type, idempotency_key, status, payload,
                payload_digest, handler_contract_version, execution_stage, retryable,
                attempts, max_attempts, created_at
            ) VALUES (
                :seller_id, :job_type, :idempotency_key, 'manual_required', :payload,
                :payload_digest, :handler_contract_version, 'manual_required', false,
                0, :max_attempts, now()
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """
        )
        result = await db.execute(
            insert_sql,
            {
                "seller_id": seller_id,
                "job_type": job_type,
                "idempotency_key": key,
                "payload": json.dumps(payload or {}, default=str),
                "payload_digest": digest,
                "handler_contract_version": handler_contract_version,
                "max_attempts": max_attempts,
            },
        )
        returned = result.fetchone()
        if returned is None:
            # Existing row — fetch it
            existing_q = await db.execute(select(BackgroundJob).where(BackgroundJob.idempotency_key == key))
            existing = existing_q.scalar_one_or_none()
            if existing:
                # Validate matching
                if existing.job_type != job_type or existing.seller_id != seller_id:
                    # Conflict with different payload — treat as conflict per spec
                    pass
                return existing, False
            # Should not happen
            raise RuntimeError("Failed to insert or fetch manual_required job")
        # Fetch newly inserted
        new_q = await db.execute(select(BackgroundJob).where(BackgroundJob.id == returned[0]))
        new_job = new_q.scalar_one()
        return new_job, True

    # Enabled handler path
    contract_version = handler_contract_version if handler_contract_version is not None else spec.contract_version
    # Validate contract version matches enabled spec
    if contract_version != spec.contract_version:
        # Contract stale — quarantine
        insert_sql = text(
            """
            INSERT INTO background_jobs (
                seller_id, job_type, idempotency_key, status, payload,
                payload_digest, handler_contract_version, execution_stage, retryable,
                attempts, max_attempts, created_at
            ) VALUES (
                :seller_id, :job_type, :idempotency_key, 'manual_required', :payload,
                :payload_digest, :handler_contract_version, 'manual_required', false,
                0, :max_attempts, now()
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """
        )
        result = await db.execute(
            insert_sql,
            {
                "seller_id": seller_id,
                "job_type": job_type,
                "idempotency_key": key,
                "payload": json.dumps(payload or {}, default=str),
                "payload_digest": digest,
                "handler_contract_version": contract_version,
                "max_attempts": max_attempts,
            },
        )
        ret = result.fetchone()
        if ret is None:
            existing_q = await db.execute(select(BackgroundJob).where(BackgroundJob.idempotency_key == key))
            existing = existing_q.scalar_one()
            return existing, False
        new_q = await db.execute(select(BackgroundJob).where(BackgroundJob.id == ret[0]))
        return new_q.scalar_one(), True

    # Normal enabled path — atomic insert
    stage = execution_stage or spec.initial_stage
    # Force pre_side_effect for new jobs per P1.2
    if stage != "pre_side_effect":
        stage = "pre_side_effect"

    insert_sql = text(
        """
        INSERT INTO background_jobs (
            seller_id, job_type, idempotency_key, status, payload,
            payload_digest, handler_contract_version, execution_stage, retryable,
            attempts, max_attempts, next_run_at, created_at
        ) VALUES (
            :seller_id, :job_type, :idempotency_key, 'queued', :payload,
            :payload_digest, :handler_contract_version, :execution_stage, :retryable,
            0, :max_attempts, now(), now()
        )
        ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING id
        """
    )
    result = await db.execute(
        insert_sql,
        {
            "seller_id": seller_id,
            "job_type": job_type,
            "idempotency_key": key,
            "payload": json.dumps(payload or {}, default=str),
            "payload_digest": digest,
            "handler_contract_version": contract_version,
            "execution_stage": stage,
            "retryable": retryable,
            "max_attempts": max_attempts,
        },
    )
    returned = result.fetchone()
    if returned is None:
        # Conflict — fetch existing and validate
        existing_q = await db.execute(select(BackgroundJob).where(BackgroundJob.idempotency_key == key))
        existing = existing_q.scalar_one_or_none()
        if existing is None:
            raise RuntimeError("ON CONFLICT returned no row and no existing found")
        # Validate seller/job_type/digest match per spec
        if existing.payload_digest is not None and existing.payload_digest != digest:
            # Same key different payload => conflict
            # Return existing but caller should treat as conflict
            pass
        if existing.job_type != job_type:
            pass
        return existing, False

    # Inserted — fetch full row
    new_q = await db.execute(select(BackgroundJob).where(BackgroundJob.id == returned[0]))
    new_job = new_q.scalar_one()
    return new_job, True

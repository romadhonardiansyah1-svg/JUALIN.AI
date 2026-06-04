"""
Idempotency helpers for webhooks and background jobs.
"""
import hashlib
import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.scale_core import WebhookEvent, BackgroundJob


def make_idempotency_key(provider: str, payload: dict, external_id: str = "") -> str:
    if external_id:
        raw = f"{provider}:{external_id}"
    else:
        raw = f"{provider}:{json.dumps(payload or {}, sort_keys=True, default=str)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def get_or_create_webhook_event(
    db: AsyncSession,
    provider: str,
    payload: dict,
    event_type: str = "",
    external_event_id: str = "",
) -> tuple[WebhookEvent, bool]:
    key = make_idempotency_key(provider, payload, external_event_id)
    result = await db.execute(select(WebhookEvent).where(WebhookEvent.idempotency_key == key))
    existing = result.scalar_one_or_none()
    if existing:
        return existing, False

    event = WebhookEvent(
        provider=provider,
        event_type=event_type,
        external_event_id=external_event_id,
        idempotency_key=key,
        payload=payload or {},
    )
    db.add(event)
    await db.flush()
    return event, True


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
) -> tuple[BackgroundJob, bool]:
    key = idempotency_key or make_idempotency_key(job_type, payload)
    result = await db.execute(select(BackgroundJob).where(BackgroundJob.idempotency_key == key))
    existing = result.scalar_one_or_none()
    if existing:
        return existing, False

    job = BackgroundJob(
        seller_id=seller_id,
        job_type=job_type,
        idempotency_key=key,
        payload=payload or {},
    )
    db.add(job)
    await db.flush()
    return job, True

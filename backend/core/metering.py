"""
Usage metering with idempotent event ledger.
Records every usage event and updates the counter atomically.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.quota import current_month_period, increment_usage
from models.usage_event import UsageEvent
from models.user import User


async def record_usage_event(
    db: AsyncSession,
    *,
    seller_id: int,
    metric: str,
    quantity: int = 1,
    source: str = "",
    source_id: str = "",
    idempotency_key: str = "",
    period: str | None = None,
    user: User | None = None,
) -> tuple[UsageEvent | None, bool]:
    """
    Record a usage event idempotently.
    Returns (event, is_new). If key already exists, returns (None, False).
    """
    period = period or current_month_period()

    if idempotency_key:
        existing = await db.execute(
            select(UsageEvent).where(UsageEvent.idempotency_key == idempotency_key)
        )
        if existing.scalar_one_or_none():
            return None, False

    event = UsageEvent(
        seller_id=seller_id,
        metric=metric,
        quantity=quantity,
        source=source,
        source_id=str(source_id),
        idempotency_key=idempotency_key or f"{metric}:{seller_id}:{source_id}:{period}",
        period=period,
    )
    db.add(event)

    # Also increment the counter for backward compatibility
    if user:
        await increment_usage(db, user=user, metric=metric, amount=quantity, period=period)

    await db.flush()
    return event, True

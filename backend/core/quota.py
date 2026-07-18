"""
Usage quota helper for SaaS limits.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.billing import UsageCounter
from models.user import User, UserTier

settings = get_settings()

TIER_LIMITS = {
    UserTier.FREE: {"chat_month": settings.QUOTA_FREE, "products": settings.PRODUCT_LIMIT_FREE, "whatsapp_channels": 0, "campaign_sends": 0},
    UserTier.STARTER: {"chat_month": settings.QUOTA_STARTER, "products": settings.PRODUCT_LIMIT_STARTER, "whatsapp_channels": 1, "campaign_sends": 200},
    UserTier.PRO: {"chat_month": settings.QUOTA_PRO, "products": settings.PRODUCT_LIMIT_PRO, "whatsapp_channels": 2, "campaign_sends": 1000},
    UserTier.BISNIS: {"chat_month": settings.QUOTA_BISNIS, "products": settings.PRODUCT_LIMIT_BISNIS, "whatsapp_channels": 5, "campaign_sends": 5000},
}


def current_month_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def get_tier_limit(user: User, metric: str) -> int:
    return TIER_LIMITS.get(user.tier, TIER_LIMITS[UserTier.FREE]).get(metric, 0)


async def lock_product_quota(db: AsyncSession, seller_id: int) -> None:
    """Serialize all active-product quota writers for one seller."""
    await db.execute(
        select(User.id).where(User.id == seller_id).with_for_update()
    )


async def check_usage_quota(
    db: AsyncSession,
    *,
    user: User,
    metric: str,
    increment: int = 1,
    period: str | None = None,
) -> dict:
    period = period or current_month_period()
    limit = get_tier_limit(user, metric)
    result = await db.execute(
        select(UsageCounter)
        .where(UsageCounter.seller_id == user.id)
        .where(UsageCounter.metric == metric)
        .where(UsageCounter.period == period)
    )
    counter = result.scalar_one_or_none()
    used = counter.used if counter else 0
    return {
        "metric": metric,
        "period": period,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "allowed": limit < 0 or used + increment <= limit,
    }


async def increment_usage(
    db: AsyncSession,
    *,
    user: User,
    metric: str,
    amount: int = 1,
    period: str | None = None,
) -> UsageCounter:
    period = period or current_month_period()
    limit = get_tier_limit(user, metric)
    result = await db.execute(
        select(UsageCounter)
        .where(UsageCounter.seller_id == user.id)
        .where(UsageCounter.metric == metric)
        .where(UsageCounter.period == period)
        .with_for_update()
    )
    counter = result.scalar_one_or_none()
    if not counter:
        counter = UsageCounter(seller_id=user.id, metric=metric, period=period, used=0, limit_value=limit)
        db.add(counter)
    counter.used += amount
    counter.limit_value = limit
    await db.flush()
    return counter

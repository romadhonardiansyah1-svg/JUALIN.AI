"""Helper kebijakan agen per-seller."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.agent_os import AgentPolicy

settings = get_settings()


async def get_or_create_policy(seller_id: int, db: AsyncSession) -> AgentPolicy:
    """Ambil AgentPolicy seller; buat default jika belum ada. Memakai flush (bukan commit)."""
    result = await db.execute(select(AgentPolicy).where(AgentPolicy.seller_id == seller_id))
    policy = result.scalar_one_or_none()
    if policy:
        return policy

    policy = AgentPolicy(
        seller_id=seller_id,
        max_discount_percent=settings.AGENT_OS_DEFAULT_MAX_DISCOUNT,
        margin_floor_percent=settings.AGENT_OS_DEFAULT_MARGIN_FLOOR,
        require_approval_above_percent=settings.AGENT_OS_APPROVAL_ABOVE_PERCENT,
        low_stock_threshold=settings.AGENT_OS_LOW_STOCK_THRESHOLD,
    )
    db.add(policy)
    await db.flush()
    return policy

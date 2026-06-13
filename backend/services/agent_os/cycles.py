"""JUALIN OS — Siklus proaktif untuk worker arq (dipanggil cron)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging_config import get_logger
from models.user import User, UserRole
from services.agent_os.policy import get_or_create_policy
from services.agent_os.inventory import scan_low_stock
from services.agent_os.growth import run_growth_cycle

logger = get_logger(__name__)


async def run_all_seller_cycles(db: AsyncSession) -> dict:
    """Jalankan inventory scan + growth cycle untuk setiap seller. Commit di sini."""
    r = await db.execute(select(User).where(User.role == UserRole.SELLER))
    sellers = r.scalars().all()
    processed = 0
    for seller in sellers:
        try:
            policy = await get_or_create_policy(seller.id, db)
            if policy.allow_low_stock_alert:
                await scan_low_stock(seller.id, db, policy.low_stock_threshold)
            if policy.allow_auto_followup:
                await run_growth_cycle(seller.id, db, policy)
            await db.commit()
            processed += 1
        except Exception as e:
            await db.rollback()
            logger.warning(f"cycle failed for seller {seller.id}: {e}")
    return {"sellers_processed": processed}

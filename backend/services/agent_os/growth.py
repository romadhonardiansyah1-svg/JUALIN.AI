"""JUALIN OS — Marketing AI (Growth): identifikasi peluang proaktif."""
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging_config import get_logger
from models.order import Order, OrderStatus
from models.crm import Customer
from models.agent_os import AgentRun

logger = get_logger(__name__)


async def run_growth_cycle(seller_id: int, db: AsyncSession, policy) -> dict:
    """
    Identifikasi (1) pembayaran tertunda yang perlu ditagih, (2) pelanggan pasif untuk win-back.
    Catat AgentRun bila ada temuan. Tidak mengirim pesan (aman tanpa kredensial WA).
    """
    now = datetime.now(timezone.utc)

    # 1. Pending payment > 1 jam
    cutoff = now - timedelta(hours=1)
    r = await db.execute(
        select(Order)
        .where(Order.seller_id == seller_id)
        .where(Order.status == OrderStatus.PENDING)
        .where(Order.created_at <= cutoff)
        .order_by(Order.created_at.asc())
        .limit(20)
    )
    pending = r.scalars().all()
    pending_value = sum(float(o.total or 0) for o in pending)

    # 2. Pelanggan pasif (last_seen > 14 hari, pernah order)
    inactive_cut = now - timedelta(days=14)
    r2 = await db.execute(
        select(Customer)
        .where(Customer.seller_id == seller_id)
        .where(Customer.total_orders > 0)
        .where(Customer.last_seen_at != None)  # noqa: E711
        .where(Customer.last_seen_at <= inactive_cut)
        .limit(20)
    )
    inactive = r2.scalars().all()

    findings = {
        "pending_orders": len(pending),
        "pending_value": round(pending_value),
        "winback_candidates": len(inactive),
    }

    if pending or inactive:
        db.add(AgentRun(
            seller_id=seller_id, agent_role="growth", trigger="cron", status="done",
            summary=(f"{len(pending)} pembayaran tertunda (Rp {pending_value:,.0f}) perlu ditagih, "
                     f"{len(inactive)} pelanggan pasif bisa di-win-back"),
            detail_json=findings,
        ))
        await db.flush()
    return findings

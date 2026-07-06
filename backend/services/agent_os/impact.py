"""JUALIN OS — metrik dampak (dipakai route /impact dan daily brief)."""
from datetime import timezone as _tz, timedelta as _td

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from models.order import Order
from models.agent_os import AgentRun


async def build_impact(seller_id: int, db: AsyncSession) -> dict:
    r = await db.execute(
        select(Order).where(Order.seller_id == seller_id).order_by(desc(Order.id)).limit(500)
    )
    orders = r.scalars().all()

    def _has_nego(o):
        return any(isinstance(it, dict) and it.get("nego") for it in (o.items if isinstance(o.items, list) else []))

    nego_orders = [o for o in orders if _has_nego(o)]
    omzet_nego = sum(float(o.total or 0) for o in nego_orders)

    wib = _tz(_td(hours=7))

    def _off_hours(dt):
        if not dt:
            return False
        h = dt.astimezone(wib).hour
        return h >= 21 or h < 8

    offline_omzet = sum(float(o.total or 0) for o in orders if _off_hours(o.created_at))
    offline_orders = len([o for o in orders if _off_hours(o.created_at)])

    r2 = await db.execute(
        select(AgentRun).where(AgentRun.seller_id == seller_id)
        .where(AgentRun.agent_role == "negotiator").order_by(desc(AgentRun.id)).limit(500)
    )
    saved = 0.0
    blocked_attempts = 0
    for run in r2.scalars().all():
        d = run.detail_json or {}
        ask, offer = d.get("customer_ask"), d.get("offer_price")
        if d.get("decision") == "counter_floor" and ask and offer and float(offer) > float(ask):
            saved += float(offer) - float(ask)
            blocked_attempts += 1

    return {
        "omzet_nego": round(omzet_nego),
        "orders_nego": len(nego_orders),
        "guardrail_saved": round(saved),
        "blocked_below_floor": blocked_attempts,
        "offline_omzet": round(offline_omzet),
        "offline_orders": offline_orders,
    }

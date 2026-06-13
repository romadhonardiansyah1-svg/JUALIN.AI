"""JUALIN OS — Keuangan AI (Finance)."""
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.order import Order

PAID_STATUSES = {"paid", "processing", "shipped", "delivered", "done"}


def _status_str(o) -> str:
    return o.status.value if hasattr(o.status, "value") else str(o.status)


async def build_finance_snapshot(seller_id: int, db: AsyncSession) -> dict:
    """Snapshot keuangan hari ini vs kemarin. Hanya membaca (tidak menulis)."""
    now = datetime.now(timezone.utc)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_yest = start_today - timedelta(days=1)

    r = await db.execute(
        select(Order).where(Order.seller_id == seller_id).where(Order.created_at >= start_yest)
    )
    orders = r.scalars().all()

    def bucket(o):
        return "today" if o.created_at and o.created_at >= start_today else "yest"

    today = [o for o in orders if bucket(o) == "today"]
    yest = [o for o in orders if bucket(o) == "yest"]

    def revenue(lst):
        return sum(float(o.total or 0) for o in lst if _status_str(o) in PAID_STATUSES)

    rev_today = revenue(today)
    rev_yest = revenue(yest)
    pending = [o for o in today if _status_str(o) == "pending"]
    pending_value = sum(float(o.total or 0) for o in pending)

    # Produk terlaris hari ini (dari items)
    counter = {}
    for o in today:
        if _status_str(o) not in PAID_STATUSES:
            continue
        for it in (o.items if isinstance(o.items, list) else []):
            nama = it.get("nama", "?")
            counter[nama] = counter.get(nama, 0) + int(it.get("qty", 1))
    top_product = max(counter.items(), key=lambda kv: kv[1])[0] if counter else None

    delta_pct = 0.0 if rev_yest <= 0 else round((rev_today - rev_yest) / rev_yest * 100, 1)
    return {
        "revenue_today": round(rev_today),
        "revenue_yesterday": round(rev_yest),
        "revenue_delta_pct": delta_pct,
        "orders_today": len(today),
        "paid_today": len([o for o in today if _status_str(o) in PAID_STATUSES]),
        "pending_today": len(pending),
        "pending_value": round(pending_value),
        "top_product": top_product,
    }

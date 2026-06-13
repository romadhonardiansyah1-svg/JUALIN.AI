"""JUALIN OS — Gudang AI (Inventory)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging_config import get_logger
from models.product import Product
from models.agent_os import AgentRun

logger = get_logger(__name__)


async def check_stock_guard(seller_id: int, items: list[dict], db: AsyncSession) -> dict:
    """Verifikasi stok cukup untuk daftar item [{product_id, qty}]. Return {ok, issues}."""
    issues = []
    for it in items or []:
        pid = it.get("product_id")
        qty = int(it.get("qty", 1))
        if not pid:
            continue
        r = await db.execute(select(Product).where(Product.id == pid, Product.seller_id == seller_id))
        p = r.scalar_one_or_none()
        if not p or p.is_active != 1:
            issues.append({"product_id": pid, "reason": "tidak ditemukan"})
        elif p.stok < qty:
            issues.append({"product_id": pid, "nama": p.nama, "reason": f"stok {p.stok} < {qty}"})
    return {"ok": len(issues) == 0, "issues": issues}


async def scan_low_stock(seller_id: int, db: AsyncSession, threshold: int = 3) -> list[dict]:
    """Pindai produk stok menipis. Catat AgentRun bila ada temuan (flush, bukan commit)."""
    r = await db.execute(
        select(Product)
        .where(Product.seller_id == seller_id)
        .where(Product.is_active == 1)
        .where(Product.stok <= threshold)
        .order_by(Product.stok.asc())
        .limit(20)
    )
    low = r.scalars().all()
    items = [{"product_id": p.id, "nama": p.nama, "stok": p.stok} for p in low]
    if items:
        db.add(AgentRun(
            seller_id=seller_id, agent_role="inventory", trigger="cron", status="done",
            summary=f"{len(items)} produk stok menipis (≤{threshold})",
            detail_json={"items": items},
        ))
        await db.flush()
    return items

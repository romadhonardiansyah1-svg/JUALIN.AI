"""
Seed tambahan JUALIN OS:
- Isi cost_price produk demo (≈60% harga) agar negosiasi berbasis margin nyata.
- Buat AgentPolicy untuk demo seller.

Jalankan SETELAH seed_data:  python -m seed.seed_agent_os
"""
import asyncio
import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from models.database import async_session, init_db
from models.user import User
from models.product import Product
from models.agent_os import AgentPolicy


async def run():
    await init_db()
    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == "demo@jualin.ai"))
        seller = result.scalar_one_or_none()
        if not seller:
            print("⚠️ Demo seller belum ada. Jalankan `python -m seed.seed_data` dulu.")
            return

        # 1. cost_price = 60% harga (kalau masih 0)
        pr = await db.execute(select(Product).where(Product.seller_id == seller.id))
        updated = 0
        for p in pr.scalars().all():
            if not getattr(p, "cost_price", 0):
                p.cost_price = round(float(p.harga) * 0.6)
                updated += 1

        # 2. AgentPolicy
        pol = (await db.execute(
            select(AgentPolicy).where(AgentPolicy.seller_id == seller.id)
        )).scalar_one_or_none()
        if not pol:
            db.add(AgentPolicy(seller_id=seller.id))
            print("✅ AgentPolicy demo dibuat")

        await db.commit()
        print(f"✅ cost_price diisi untuk {updated} produk. JUALIN OS siap didemokan.")


if __name__ == "__main__":
    asyncio.run(run())

"""
JUALIN.AI — Customer Memory Service
Ringan: simpan ringkasan ~200 byte per customer, bukan full history
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from datetime import datetime, timezone

from models.customer_memory import CustomerMemory


async def find_customer(
    seller_id: int,
    db: AsyncSession,
    phone: str = "",
    name: str = "",
    session_id: str = "",
) -> CustomerMemory | None:
    """
    Cari customer yang pernah chat sebelumnya.
    Prioritas match: phone > name > session_id
    """
    # 1. Match by phone (paling akurat)
    if phone:
        result = await db.execute(
            select(CustomerMemory)
            .where(CustomerMemory.seller_id == seller_id)
            .where(CustomerMemory.phone == phone)
        )
        customer = result.scalar_one_or_none()
        if customer:
            return customer

    # 2. Match by name (case-insensitive)
    if name and name != "Customer":
        result = await db.execute(
            select(CustomerMemory)
            .where(CustomerMemory.seller_id == seller_id)
            .where(CustomerMemory.name == name)
        )
        customer = result.scalar_one_or_none()
        if customer:
            return customer

    # 3. Not found
    return None


async def get_or_create_memory(
    seller_id: int,
    session_id: str,
    db: AsyncSession,
    phone: str = "",
    name: str = "Customer",
) -> tuple[CustomerMemory, bool]:
    """
    Get existing customer or create new memory.
    Returns (memory, is_returning).
    """
    # Try find existing
    existing = await find_customer(seller_id, db, phone=phone, name=name)

    if existing:
        # Returning customer!
        existing.visit_count += 1
        existing.last_visit = datetime.now(timezone.utc)

        # Add session_id to list (keep last 10)
        sessions = existing.session_ids or []
        if session_id not in sessions:
            sessions.append(session_id)
            existing.session_ids = sessions[-10:]  # Keep last 10 only

        # Update name/phone if now provided
        if phone and not existing.phone:
            existing.phone = phone
        if name != "Customer" and existing.name == "Customer":
            existing.name = name

        await db.commit()
        return existing, True

    # New customer
    memory = CustomerMemory(
        seller_id=seller_id,
        phone=phone,
        name=name,
        session_ids=[session_id],
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)
    return memory, False


async def update_memory_after_order(
    memory: CustomerMemory,
    order_items: list[dict],
    order_total: float,
    db: AsyncSession,
):
    """
    Update memory setelah order selesai.
    Simpan RINGKASAN saja, bukan full data.
    """
    memory.total_orders += 1
    memory.total_spent += order_total

    # Update last_products (keep 5 terbaru)
    products = memory.last_products or []
    for item in order_items:
        nama = item.get("nama", "")
        if nama and nama not in products:
            products.append(nama)
    memory.last_products = products[-5:]  # Max 5

    # Extract preferences (dari nama produk — kata kunci)
    prefs = memory.preferences or []
    keywords = []
    for item in order_items:
        nama = item.get("nama", "").lower()
        # Extract warna, ukuran, style
        for word in nama.split():
            if len(word) > 2 and word not in ["dan", "atau", "untuk", "yang", "baju", "kaos"]:
                keywords.append(word)
    for kw in keywords:
        if kw not in prefs:
            prefs.append(kw)
    memory.preferences = prefs[-5:]  # Max 5

    await db.commit()


def format_memory_context(memory: CustomerMemory, is_returning: bool) -> str:
    """
    Format memory jadi konteks singkat untuk AI prompt.
    Output: 2-3 baris teks saja.
    """
    if not is_returning:
        return ""

    lines = ["\n## CUSTOMER MEMORY (customer ini pernah chat sebelumnya!)"]
    lines.append(f"- Nama: {memory.name}")
    lines.append(f"- Kunjungan ke-{memory.visit_count}")

    if memory.total_orders > 0:
        lines.append(f"- Pernah order {memory.total_orders}x, total belanja Rp {memory.total_spent:,.0f}")

    if memory.last_products:
        lines.append(f"- Produk terakhir dibeli: {', '.join(memory.last_products)}")

    if memory.preferences:
        lines.append(f"- Preferensi: {', '.join(memory.preferences)}")

    lines.append("- INSTRUKSI: Sapa customer dengan menyebut nama, tanyakan kabar, dan tawarkan produk relevan berdasarkan preferensi.")

    return "\n".join(lines)

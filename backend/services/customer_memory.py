"""
JUALIN.AI — Customer Memory Service
Lightweight customer profiling: ~300 bytes per customer, not full history.

Features:
- Find returning customers by phone > name > session
- Auto-tagging (repeat_buyer, high_value, etc.)
- Preference extraction from order history
- Contextual prompt injection for AI personalization
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from models.customer_memory import CustomerMemory
from core.logging_config import get_logger

logger = get_logger(__name__)


async def find_customer(
    seller_id: int,
    db: AsyncSession,
    phone: str = "",
    name: str = "",
    session_id: str = "",
) -> CustomerMemory | None:
    """
    Find customer by identifiers, priority: phone > name > session.
    Returns None if not found.
    """
    # 1. Match by phone (most accurate)
    if phone:
        result = await db.execute(
            select(CustomerMemory)
            .where(CustomerMemory.seller_id == seller_id)
            .where(CustomerMemory.phone == phone)
        )
        customer = result.scalar_one_or_none()
        if customer:
            return customer

    # 2. Match by name (case-sensitive, skip generic)
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
    Get existing customer memory or create new one.
    Returns (memory, is_returning_customer).
    """
    existing = await find_customer(seller_id, db, phone=phone, name=name)

    if existing:
        # Returning customer
        existing.visit_count += 1
        existing.last_visit = datetime.now(timezone.utc)

        # Track session IDs (keep last 10)
        sessions = existing.session_ids or []
        if session_id not in sessions:
            sessions.append(session_id)
            existing.session_ids = sessions[-10:]

        # Update name/phone if newly provided
        if phone and not existing.phone:
            existing.phone = phone
        if name != "Customer" and existing.name == "Customer":
            existing.name = name

        # Auto-update tags
        _update_auto_tags(existing)

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
    Update memory after an order is placed.
    Stores SUMMARY only, not full data.
    """
    memory.total_orders += 1
    memory.total_spent += order_total

    # Update last products (keep 5 most recent)
    products = memory.last_products or []
    for item in order_items:
        nama = item.get("nama", "")
        if nama and nama not in products:
            products.append(nama)
    memory.last_products = products[-5:]

    # Extract preferences from product names
    prefs = memory.preferences or []
    keywords = []
    skip_words = {"dan", "atau", "untuk", "yang", "baju", "kaos", "celana", "dengan", "dari"}
    for item in order_items:
        nama = item.get("nama", "").lower()
        for word in nama.split():
            if len(word) > 2 and word not in skip_words:
                keywords.append(word)
    for kw in keywords:
        if kw not in prefs:
            prefs.append(kw)
    memory.preferences = prefs[-5:]

    # Auto-update tags
    _update_auto_tags(memory)

    await db.commit()
    logger.info(
        f"Customer memory updated after order",
        extra={
            "customer_name": memory.name,
            "total_orders": memory.total_orders,
            "total_spent": memory.total_spent,
        },
    )


def _update_auto_tags(memory: CustomerMemory):
    """
    Auto-generate customer tags based on behavior.
    Tags help AI personalize responses without reading full history.
    """
    tags = set(memory.tags or [])

    # Repeat buyer
    if memory.total_orders >= 2:
        tags.add("repeat_buyer")

    # High value customer (spent > 500K)
    if memory.total_spent >= 500_000:
        tags.add("high_value")

    # VIP customer (5+ orders)
    if memory.total_orders >= 5:
        tags.add("vip")
        tags.discard("repeat_buyer")  # VIP supersedes repeat_buyer

    # Frequent visitor (5+ visits)
    if memory.visit_count >= 5:
        tags.add("frequent_visitor")

    # Window shopper (many visits, no orders)
    if memory.visit_count >= 3 and memory.total_orders == 0:
        tags.add("window_shopper")

    memory.tags = sorted(list(tags))[:8]  # Max 8 tags


def format_memory_context(memory: CustomerMemory, is_returning: bool) -> str:
    """
    Format memory into a compact context string for AI prompt injection.
    Output: 3-5 lines of actionable context.
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

    # Tag-based instructions
    tags = set(memory.tags or [])
    if "vip" in tags:
        lines.append("- 🌟 VIP CUSTOMER! Berikan pelayanan ekstra spesial dan tawarkan produk premium.")
    elif "high_value" in tags:
        lines.append("- 💎 High-value customer. Berikan perhatian ekstra.")
    elif "repeat_buyer" in tags:
        lines.append("- 🔄 Repeat buyer. Tawarkan produk baru atau yang berhubungan dengan pembelian sebelumnya.")

    if "window_shopper" in tags:
        lines.append("- 👀 Sering kunjungi tapi belum pernah order. Berikan dorongan halus untuk mencoba.")

    lines.append("- INSTRUKSI: Sapa customer dengan menyebut nama, tanyakan kabar, dan tawarkan produk relevan berdasarkan preferensi.")

    return "\n".join(lines)

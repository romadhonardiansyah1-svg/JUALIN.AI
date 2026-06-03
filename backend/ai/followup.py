"""
JUALIN.AI — Follow-up Logic
Auto-remind customers who haven't paid
"""
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from models.order import Order, OrderStatus
from models.conversation import Conversation


FOLLOWUP_MESSAGES = [
    # 1st follow-up (after 1 hour)
    "Hai kak! 😊 Mau dibantu selesaikan ordernya? "
    "Kami sudah siapkan pesanannya. Tinggal transfer ya kak! 🙏",
    
    # 2nd follow-up (after 6 hours)
    "Kak, pesanan kakak masih kami simpan nih 📦 "
    "Jangan sampai kehabisan ya! Mau lanjutkan ordernya? 😊",
    
    # 3rd follow-up (after 24 hours)
    "Hai kak, ini reminder terakhir untuk pesanan kakak. "
    "Kalau sudah tidak berminat, kami cancel ya. Terima kasih kak! 🙏",
]


async def get_pending_followups(db: AsyncSession) -> list[dict]:
    """
    Get orders that need follow-up.
    Rules:
    - Status: PENDING
    - Created > 1 hour ago
    - Max 3 follow-ups
    - At least 1 hour between follow-ups
    """
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    
    result = await db.execute(
        select(Order).where(
            and_(
                Order.status == OrderStatus.PENDING,
                Order.created_at < one_hour_ago,
                Order.followup_count < 3,
            )
        ).order_by(Order.created_at)
    )
    orders = result.scalars().all()
    
    followups = []
    for order in orders:
        # Check if enough time has passed since last follow-up
        if order.last_followup_at:
            # Properly handle timezone: use as-is if aware, assume UTC if naive (BUG 11 FIX)
            last_fu = order.last_followup_at
            if last_fu.tzinfo is None:
                last_fu = last_fu.replace(tzinfo=timezone.utc)
            time_since = datetime.now(timezone.utc) - last_fu
            intervals = [timedelta(hours=1), timedelta(hours=6), timedelta(hours=24)]
            required_wait = intervals[min(order.followup_count, 2)]
            if time_since < required_wait:
                continue
        
        message = FOLLOWUP_MESSAGES[min(order.followup_count, 2)]
        
        # Add order-specific details
        items_text = order.items if isinstance(order.items, str) else str(order.items)
        message += f"\n\n📋 Detail order:\n{items_text}\n💰 Total: Rp {order.total:,.0f}"
        
        followups.append({
            "order_id": order.id,
            "seller_id": order.seller_id,
            "customer_name": order.customer_name,
            "customer_phone": order.customer_phone,
            "message": message,
            "followup_number": order.followup_count + 1,
            "conversation_id": order.conversation_id if hasattr(order, 'conversation_id') else None,
        })
    
    return followups


async def mark_followup_sent(order_id: int, db: AsyncSession):
    """Mark an order as having received a follow-up."""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    
    if order:
        order.followup_count += 1
        order.last_followup_at = datetime.now(timezone.utc)
        await db.commit()


async def auto_cancel_expired(db: AsyncSession) -> int:
    """
    Auto-cancel orders that have been pending for > 48 hours
    and have received all 3 follow-ups.
    Returns number of cancelled orders.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    
    result = await db.execute(
        select(Order).where(
            and_(
                Order.status == OrderStatus.PENDING,
                Order.created_at < cutoff,
                Order.followup_count >= 3,
            )
        )
    )
    orders = result.scalars().all()
    
    from models.product import Product
    count = 0
    for order in orders:
        order.status = OrderStatus.CANCELLED
        order.notes = (order.notes or "") + " [Auto-cancelled: tidak ada pembayaran setelah 48 jam]"
        
        # restore stock
        items = order.items if isinstance(order.items, list) else []
        for item in items:
            if "product_id" in item:
                prod_result = await db.execute(
                    select(Product).where(Product.id == item["product_id"])
                )
                product = prod_result.scalar_one_or_none()
                if product:
                    product.stok += item.get("qty", 1)
        
        count += 1
    
    if count > 0:
        await db.commit()
    
    return count

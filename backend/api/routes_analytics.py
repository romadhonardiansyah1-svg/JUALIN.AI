"""
JUALIN.AI — Analytics API Routes
Dashboard statistics for sellers
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from datetime import datetime, timedelta, timezone

from models.database import get_db
from models.user import User
from models.product import Product
from models.conversation import Conversation, Message
from models.order import Order, OrderStatus
from api.routes_auth import get_current_user

router = APIRouter()


@router.get("/summary")
async def get_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard summary stats for the current seller."""
    seller_id = current_user.id
    today = datetime.now(timezone.utc).date()
    
    # Total chats today
    chat_today = await db.execute(
        select(func.count(Conversation.id))
        .where(Conversation.seller_id == seller_id)
        .where(func.date(Conversation.created_at) == today)
    )
    
    # Total orders today
    orders_today = await db.execute(
        select(func.count(Order.id))
        .where(Order.seller_id == seller_id)
        .where(func.date(Order.created_at) == today)
    )
    
    # Revenue today
    revenue_today = await db.execute(
        select(func.coalesce(func.sum(Order.total), 0))
        .where(Order.seller_id == seller_id)
        .where(func.date(Order.created_at) == today)
        .where(Order.status != OrderStatus.CANCELLED)
    )
    
    # Active products
    products_active = await db.execute(
        select(func.count(Product.id))
        .where(Product.seller_id == seller_id)
        .where(Product.is_active == 1)
    )
    
    # Pending orders (unpaid)
    orders_pending = await db.execute(
        select(func.count(Order.id))
        .where(Order.seller_id == seller_id)
        .where(Order.status == OrderStatus.PENDING)
    )
    
    # Total messages today (for avg response calc)
    messages_today = await db.execute(
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.seller_id == seller_id)
        .where(func.date(Message.created_at) == today)
    )
    
    return {
        "chat_today": chat_today.scalar() or 0,
        "orders_today": orders_today.scalar() or 0,
        "revenue_today": revenue_today.scalar() or 0,
        "products_active": products_active.scalar() or 0,
        "orders_pending": orders_pending.scalar() or 0,
        "messages_today": messages_today.scalar() or 0,
        "avg_response_time": 3,  # Simulated: 3 seconds
    }


@router.get("/orders-daily")
async def get_orders_daily(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get order count per day for chart (optimized: single query instead of N)."""
    seller_id = current_user.id
    start_date = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
    
    # Single query: group by date
    count_result = await db.execute(
        select(func.date(Order.created_at).label("order_date"), func.count(Order.id).label("cnt"))
        .where(Order.seller_id == seller_id)
        .where(func.date(Order.created_at) >= start_date)
        .group_by(func.date(Order.created_at))
    )
    counts_map = {str(row.order_date): row.cnt for row in count_result.all()}
    
    # Fill in all days (including zero-count days)
    result = []
    for i in range(days - 1, -1, -1):
        date = datetime.now(timezone.utc).date() - timedelta(days=i)
        result.append({
            "date": date.isoformat(),
            "count": counts_map.get(str(date), 0),
        })
    
    return result


@router.get("/top-products")
async def get_top_products(
    limit: int = 5,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get most popular products by actual sales from orders."""
    seller_id = current_user.id
    
    # Count actual sales from Order.items JSON (BUG 10 FIX)
    result = await db.execute(
        select(Order)
        .where(Order.seller_id == seller_id)
        .where(Order.status != OrderStatus.CANCELLED)
        .order_by(Order.created_at.desc())
        .limit(100)
    )
    orders = result.scalars().all()
    
    product_counts = {}
    for order in orders:
        items = order.items if isinstance(order.items, list) else []
        for item in items:
            name = item.get("nama", "Unknown")
            product_counts[name] = product_counts.get(name, 0) + item.get("qty", 1)
    
    sorted_products = sorted(product_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    
    return [{"nama": name, "count": count} for name, count in sorted_products]

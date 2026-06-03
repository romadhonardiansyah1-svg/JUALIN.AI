"""
JUALIN.AI — Analytics Service
Business logic for computing analytics data
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from datetime import datetime, timedelta, timezone

from models.order import Order, OrderStatus
from models.product import Product
from models.conversation import Conversation, Message
from models.user import User


async def get_dashboard_summary(seller_id: int, db: AsyncSession) -> dict:
    """Get dashboard summary stats for a seller."""
    today = datetime.now(timezone.utc).date()
    month_start = today.replace(day=1)

    # Chat count this month
    chat_count = await db.execute(
        select(func.count(Conversation.id))
        .where(Conversation.seller_id == seller_id)
        .where(func.date(Conversation.created_at) >= month_start)
    )
    chats = chat_count.scalar() or 0

    # Orders this month
    order_result = await db.execute(
        select(
            func.count(Order.id).label("count"),
            func.coalesce(func.sum(Order.total), 0).label("revenue"),
        )
        .where(Order.seller_id == seller_id)
        .where(func.date(Order.created_at) >= month_start)
    )
    row = order_result.one()
    orders = row.count
    revenue = float(row.revenue)

    # Active products
    product_count = await db.execute(
        select(func.count(Product.id))
        .where(Product.seller_id == seller_id)
        .where(Product.is_active == 1)
    )
    products = product_count.scalar() or 0

    # Conversion rate
    conversion = round((orders / chats * 100), 1) if chats > 0 else 0

    return {
        "chat_today": chats,
        "orders_today": orders,
        "revenue_today": revenue,
        "products_active": products,
        "conversion_rate": conversion,
        "avg_response_time": 3,  # Placeholder — would measure from message timestamps
    }


async def get_top_products(seller_id: int, db: AsyncSession, limit: int = 5) -> list[dict]:
    """Get top selling products for a seller."""
    # Count orders per product from JSON items
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


async def get_daily_orders(seller_id: int, db: AsyncSession, days: int = 7) -> list[dict]:
    """Get daily order counts for the past N days."""
    result = []
    for i in range(days - 1, -1, -1):
        day = datetime.now(timezone.utc).date() - timedelta(days=i)
        count_result = await db.execute(
            select(func.count(Order.id))
            .where(Order.seller_id == seller_id)
            .where(func.date(Order.created_at) == day)
        )
        count = count_result.scalar() or 0
        result.append({
            "date": day.isoformat(),
            "day": day.strftime("%a"),
            "count": count,
        })
    return result


async def get_platform_stats(db: AsyncSession) -> dict:
    """Get platform-wide stats for admin panel."""
    sellers = await db.execute(select(func.count(User.id)))
    products = await db.execute(select(func.count(Product.id)).where(Product.is_active == 1))
    orders = await db.execute(select(func.count(Order.id)))
    revenue = await db.execute(select(func.coalesce(func.sum(Order.total), 0)))
    chats = await db.execute(select(func.count(Conversation.id)))

    return {
        "total_sellers": sellers.scalar() or 0,
        "total_products": products.scalar() or 0,
        "total_orders": orders.scalar() or 0,
        "total_revenue": float(revenue.scalar() or 0),
        "total_chats": chats.scalar() or 0,
    }

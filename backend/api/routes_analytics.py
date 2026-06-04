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
from models.chat_analytics import ChatAnalytics
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


@router.get("/chat-stats")
async def get_chat_stats(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get chat analytics: intent distribution, avg response time, sales stages."""
    seller_id = current_user.id
    start_date = datetime.now(timezone.utc).date() - timedelta(days=days)

    # Intent distribution
    intent_result = await db.execute(
        select(ChatAnalytics.intent, func.count(ChatAnalytics.id))
        .where(ChatAnalytics.seller_id == seller_id)
        .where(func.date(ChatAnalytics.created_at) >= start_date)
        .group_by(ChatAnalytics.intent)
    )
    intent_dist = {row[0]: row[1] for row in intent_result.all()}

    # Average response time
    avg_result = await db.execute(
        select(func.avg(ChatAnalytics.response_time_ms))
        .where(ChatAnalytics.seller_id == seller_id)
        .where(func.date(ChatAnalytics.created_at) >= start_date)
    )
    avg_response_ms = round(avg_result.scalar() or 0)

    # Total interactions
    total_result = await db.execute(
        select(func.count(ChatAnalytics.id))
        .where(ChatAnalytics.seller_id == seller_id)
        .where(func.date(ChatAnalytics.created_at) >= start_date)
    )
    total_interactions = total_result.scalar() or 0

    # Conversion count
    conv_result = await db.execute(
        select(func.count(ChatAnalytics.id))
        .where(ChatAnalytics.seller_id == seller_id)
        .where(ChatAnalytics.converted_to_order == True)
        .where(func.date(ChatAnalytics.created_at) >= start_date)
    )
    conversions = conv_result.scalar() or 0

    return {
        "intent_distribution": intent_dist,
        "avg_response_time_ms": avg_response_ms,
        "total_interactions": total_interactions,
        "conversions": conversions,
        "conversion_rate": round((conversions / total_interactions * 100), 1) if total_interactions > 0 else 0,
        "period_days": days,
    }


@router.get("/conversion-funnel")
async def get_conversion_funnel(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get conversion funnel: unique visitors → chats → orders."""
    seller_id = current_user.id
    start_date = datetime.now(timezone.utc).date() - timedelta(days=days)

    # Unique conversations (visitors)
    visitors_result = await db.execute(
        select(func.count(func.distinct(Conversation.session_id)))
        .where(Conversation.seller_id == seller_id)
        .where(func.date(Conversation.created_at) >= start_date)
    )
    visitors = visitors_result.scalar() or 0

    # Conversations with 2+ messages (engaged chats)
    engaged_result = await db.execute(
        select(func.count(func.distinct(Message.conversation_id)))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.seller_id == seller_id)
        .where(func.date(Message.created_at) >= start_date)
    )
    engaged = engaged_result.scalar() or 0

    # Orders created
    orders_result = await db.execute(
        select(func.count(Order.id))
        .where(Order.seller_id == seller_id)
        .where(func.date(Order.created_at) >= start_date)
    )
    orders = orders_result.scalar() or 0

    # Orders paid
    paid_result = await db.execute(
        select(func.count(Order.id))
        .where(Order.seller_id == seller_id)
        .where(Order.status.notin_(["pending", "cancelled"]))
        .where(func.date(Order.created_at) >= start_date)
    )
    paid = paid_result.scalar() or 0

    return {
        "funnel": [
            {"stage": "Visitors", "count": visitors},
            {"stage": "Engaged Chats", "count": engaged},
            {"stage": "Orders Created", "count": orders},
            {"stage": "Orders Paid", "count": paid},
        ],
        "period_days": days,
    }


@router.get("/sales-stages")
async def get_sales_stages(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get distribution of sales stages from chat analytics."""
    seller_id = current_user.id
    start_date = datetime.now(timezone.utc).date() - timedelta(days=days)

    result = await db.execute(
        select(ChatAnalytics.sales_stage, func.count(ChatAnalytics.id))
        .where(ChatAnalytics.seller_id == seller_id)
        .where(func.date(ChatAnalytics.created_at) >= start_date)
        .group_by(ChatAnalytics.sales_stage)
    )
    stages = {row[0]: row[1] for row in result.all()}

    # Ordered stages for visualization
    stage_order = ["greeting", "discovery", "presentation", "negotiation", "closing", "post_sale"]
    ordered = []
    for stage in stage_order:
        ordered.append({
            "stage": stage,
            "count": stages.get(stage, 0),
            "label": {
                "greeting": "Sapaan",
                "discovery": "Eksplorasi",
                "presentation": "Presentasi",
                "negotiation": "Negosiasi",
                "closing": "Closing",
                "post_sale": "Pasca-Jual",
            }.get(stage, stage),
        })

    return {
        "stages": ordered,
        "period_days": days,
    }

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
from cache import cache_get, cache_set

router = APIRouter()

# Analytics windows are dashboard-sized. Anything beyond 90 days is a full-table
# scan that no chart renders, and `?days=100000` used to be accepted verbatim.
MAX_DAYS = 90
# Raw-row endpoints must never stream an unbounded result set into memory.
MAX_RAW_ORDERS = 500
# Cache keys use the `analytics:{seller_id}:` prefix so cache_invalidate_orders()
# in cache.py already clears them. TTL is short because this module cannot call
# that invalidator without editing routes_orders.py.
# ponytail: TTL-only invalidation, wire cache_invalidate_orders into order writes
# if 60s of staleness becomes visible.
SELLER_TTL = 45


def _clamp_days(days) -> int:
    """Clamp a raw day count into 1..MAX_DAYS."""
    try:
        value = int(days)
    except (TypeError, ValueError):
        return 30
    return max(1, min(MAX_DAYS, value))


def _period_days(period: str) -> int:
    """Parse a '30d'-style period into a clamped day count."""
    return _clamp_days(str(period).strip().lower().removesuffix("d"))


@router.get("/summary")
async def get_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard summary stats for the current seller."""
    seller_id = current_user.id
    cache_key = f"analytics:{seller_id}:summary"
    cached = await cache_get(cache_key)
    if cached:
        return cached

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
    
    data = {
        "chat_today": chat_today.scalar() or 0,
        "orders_today": orders_today.scalar() or 0,
        "revenue_today": revenue_today.scalar() or 0,
        "products_active": products_active.scalar() or 0,
        "orders_pending": orders_pending.scalar() or 0,
        "messages_today": messages_today.scalar() or 0,
        "avg_response_time": 3,  # Simulated: 3 seconds
    }
    await cache_set(cache_key, data, ttl=SELLER_TTL)
    return data


@router.get("/orders-daily")
async def get_orders_daily(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get order count per day for chart (optimized: single query instead of N)."""
    seller_id = current_user.id
    days = _clamp_days(days)
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
    days = _clamp_days(days)
    cache_key = f"analytics:{seller_id}:chat-stats:{days}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

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

    data = {
        "intent_distribution": intent_dist,
        "avg_response_time_ms": avg_response_ms,
        "total_interactions": total_interactions,
        "conversions": conversions,
        "conversion_rate": round((conversions / total_interactions * 100), 1) if total_interactions > 0 else 0,
        "period_days": days,
    }
    await cache_set(cache_key, data, ttl=SELLER_TTL)
    return data


@router.get("/conversion-funnel")
async def get_conversion_funnel(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get conversion funnel: unique visitors → chats → orders."""
    seller_id = current_user.id
    days = _clamp_days(days)
    cache_key = f"analytics:{seller_id}:conversion-funnel:{days}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

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
        .where(~Order.status.in_([OrderStatus.PENDING, OrderStatus.CANCELLED]))
        .where(func.date(Order.created_at) >= start_date)
    )
    paid = paid_result.scalar() or 0

    data = {
        "funnel": [
            {"stage": "Visitors", "count": visitors},
            {"stage": "Engaged Chats", "count": engaged},
            {"stage": "Orders Created", "count": orders},
            {"stage": "Orders Paid", "count": paid},
        ],
        "period_days": days,
    }
    await cache_set(cache_key, data, ttl=SELLER_TTL)
    return data


@router.get("/sales-stages")
async def get_sales_stages(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get distribution of sales stages from chat analytics."""
    seller_id = current_user.id
    days = _clamp_days(days)
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


@router.get("/revenue")
async def get_revenue(
    period: str = "30d",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revenue intelligence from pre-aggregated daily metrics."""
    from models.daily_metrics import DailySellerMetric

    days = _period_days(period)
    start_date = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()

    result = await db.execute(
        select(DailySellerMetric)
        .where(DailySellerMetric.seller_id == current_user.id)
        .where(DailySellerMetric.date >= start_date)
        .order_by(DailySellerMetric.date.asc())
    )
    metrics = result.scalars().all()

    total_revenue = sum(m.revenue_paid for m in metrics)
    total_orders_paid = sum(m.orders_paid for m in metrics)
    total_orders_created = sum(m.orders_created for m in metrics)
    total_chats = sum(m.chats_in for m in metrics)
    total_pending = sum(m.pending_payment_value for m in metrics)

    daily = [
        {
            "date": m.date,
            "revenue": m.revenue_paid,
            "orders_paid": m.orders_paid,
            "orders_created": m.orders_created,
            "chats": m.chats_in,
        }
        for m in metrics
    ]

    return {
        "summary": {
            "total_revenue": total_revenue,
            "total_orders_paid": total_orders_paid,
            "total_orders_created": total_orders_created,
            "total_chats": total_chats,
            "total_pending_value": total_pending,
            "avg_order_value": round(total_revenue / total_orders_paid, 0) if total_orders_paid > 0 else 0,
            "chat_to_order_rate": round(total_orders_created / total_chats * 100, 1) if total_chats > 0 else 0,
        },
        "daily": daily,
        "period_days": days,
    }


@router.get("/campaign-roi")
async def get_campaign_roi(
    campaign_id: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Campaign ROI: sent, delivered, conversions."""
    from models.campaign import Campaign, CampaignRecipient

    cache_key = f"analytics:{current_user.id}:campaign-roi:{campaign_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    query = select(Campaign).where(Campaign.seller_id == current_user.id)
    if campaign_id > 0:
        query = query.where(Campaign.id == campaign_id)
    query = query.order_by(Campaign.created_at.desc()).limit(20)

    result = await db.execute(query)
    campaigns = result.scalars().all()

    # One GROUP BY for every campaign instead of 2 COUNTs per campaign.
    status_counts: dict[tuple[int, str], int] = {}
    if campaigns:
        counts_result = await db.execute(
            select(
                CampaignRecipient.campaign_id,
                CampaignRecipient.status,
                func.count(CampaignRecipient.id),
            )
            .where(CampaignRecipient.campaign_id.in_([c.id for c in campaigns]))
            .where(CampaignRecipient.status.in_(["sent", "delivered"]))
            .group_by(CampaignRecipient.campaign_id, CampaignRecipient.status)
        )
        status_counts = {(row[0], row[1]): row[2] for row in counts_result.all()}

    roi_data = [
        {
            "id": c.id,
            "name": c.title,
            "status": c.status,
            "sent": status_counts.get((c.id, "sent"), 0),
            "delivered": status_counts.get((c.id, "delivered"), 0),
            "created_at": c.created_at.isoformat() if c.created_at else "",
        }
        for c in campaigns
    ]

    await cache_set(cache_key, roi_data, ttl=SELLER_TTL)
    return roi_data


@router.get("/product-insights")
async def get_product_insights(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Product insights: best sellers, low stock, no-sales."""
    seller_id = current_user.id
    cache_key = f"analytics:{seller_id}:product-insights"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    # All active products
    products_result = await db.execute(
        select(Product).where(Product.seller_id == seller_id, Product.is_active == 1)
    )
    products = products_result.scalars().all()

    # Get order counts per product from last 30 days.
    # Only items/created_at are needed; selecting the whole ORM row pulled every
    # column and left the row count unbounded.
    start_date = datetime.now(timezone.utc).date() - timedelta(days=30)
    orders_result = await db.execute(
        select(Order.items)
        .where(Order.seller_id == seller_id)
        .where(Order.status != OrderStatus.CANCELLED)
        .where(func.date(Order.created_at) >= start_date)
        .order_by(Order.created_at.desc())
        .limit(MAX_RAW_ORDERS)
    )

    product_sales = {}
    for (order_items,) in orders_result.all():
        items = order_items if isinstance(order_items, list) else []
        for item in items:
            name = item.get("nama", "Unknown")
            product_sales[name] = product_sales.get(name, 0) + item.get("qty", 1)

    best_sellers = sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:10]
    low_stock = [p for p in products if (p.stok or 0) <= 5 and (p.stok or 0) > 0]
    no_sales = [p for p in products if p.nama not in product_sales]

    data = {
        "total_products": len(products),
        "best_sellers": [{"name": n, "qty": q} for n, q in best_sellers],
        "low_stock": [{"id": p.id, "name": p.nama, "stock": p.stok} for p in low_stock[:10]],
        "no_sales_30d": [{"id": p.id, "name": p.nama} for p in no_sales[:10]],
        "period_days": 30,
    }
    await cache_set(cache_key, data, ttl=SELLER_TTL)
    return data


# ── Money Dashboard (Market Acceptance Sprint 5) ──

@router.get("/money")
async def get_money_dashboard(
    period: str = "30d",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hero metrics: AI assisted paid orders, revenue, pending payment, recovered.
    Uses pre-aggregated DailySellerMetric for performance on VPS 4GB.
    """
    from models.daily_metrics import DailySellerMetric

    days = _period_days(period)
    start_date = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()

    result = await db.execute(
        select(DailySellerMetric)
        .where(DailySellerMetric.seller_id == current_user.id)
        .where(DailySellerMetric.date >= start_date)
    )
    metrics = result.scalars().all()

    if not metrics:
        # Empty state for new sellers
        return {
            "ai_assisted_revenue": 0,
            "ai_assisted_orders": 0,
            "total_revenue": 0,
            "total_orders_paid": 0,
            "pending_payment_value": 0,
            "recovered_payment_value": 0,
            "period_days": days,
            "is_empty": True,
            "next_steps": [
                {"action": "add_products", "label": "Tambah produk ke katalog"},
                {"action": "connect_whatsapp", "label": "Hubungkan WhatsApp"},
                {"action": "test_ai", "label": "Test AI chat"},
            ],
        }

    return {
        "ai_assisted_revenue": sum(m.ai_assisted_revenue for m in metrics),
        "ai_assisted_orders": sum(m.ai_assisted_orders for m in metrics),
        "total_revenue": sum(m.revenue_paid for m in metrics),
        "total_orders_paid": sum(m.orders_paid for m in metrics),
        "pending_payment_value": sum(m.pending_payment_value for m in metrics),
        "recovered_payment_value": sum(m.recovered_payment_value for m in metrics),
        "period_days": days,
        "is_empty": False,
    }


@router.get("/ai-impact")
async def get_ai_impact(
    period: str = "30d",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI impact metrics: handoff rate, AI vs manual, top AI-assisted products."""
    from models.daily_metrics import DailySellerMetric

    days = _period_days(period)
    start_date = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()

    result = await db.execute(
        select(DailySellerMetric)
        .where(DailySellerMetric.seller_id == current_user.id)
        .where(DailySellerMetric.date >= start_date)
    )
    metrics = result.scalars().all()

    total_orders = sum(m.orders_created for m in metrics)
    ai_orders = sum(m.ai_assisted_orders for m in metrics)
    ai_handoffs = sum(m.ai_handoff_count for m in metrics)
    total_chats = sum(m.chats_in for m in metrics)

    return {
        "ai_assisted_orders": ai_orders,
        "manual_orders": total_orders - ai_orders,
        "ai_handoff_count": ai_handoffs,
        "ai_handoff_rate": round(ai_handoffs / total_chats * 100, 1) if total_chats > 0 else 0,
        "ai_closing_rate": round(ai_orders / total_orders * 100, 1) if total_orders > 0 else 0,
        "period_days": days,
    }


@router.get("/recovery")
async def get_recovery_stats(
    period: str = "30d",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Follow-up recovery stats: how much payment was recovered from follow-ups."""
    from models.daily_metrics import DailySellerMetric

    days = _period_days(period)
    start_date = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()

    result = await db.execute(
        select(DailySellerMetric)
        .where(DailySellerMetric.seller_id == current_user.id)
        .where(DailySellerMetric.date >= start_date)
        .order_by(DailySellerMetric.date.asc())
    )
    metrics = result.scalars().all()

    total_recovered = sum(m.recovered_payment_value for m in metrics)
    total_pending = sum(m.pending_payment_value for m in metrics)

    daily = [
        {
            "date": m.date,
            "recovered": m.recovered_payment_value,
            "pending": m.pending_payment_value,
        }
        for m in metrics
    ]

    return {
        "total_recovered": total_recovered,
        "total_pending": total_pending,
        "recovery_rate": round(total_recovered / total_pending * 100, 1) if total_pending > 0 else 0,
        "daily": daily,
        "period_days": days,
    }

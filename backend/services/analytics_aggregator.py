"""
Analytics aggregation service.
Pre-computes daily seller metrics from raw data.
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging_config import get_logger
from models.daily_metrics import DailySellerMetric
from models.conversation import Conversation, Message, MessageRole
from models.order import Order, OrderStatus
from models.campaign import CampaignMessage
from models.crm import Customer
from models.user import User

logger = get_logger(__name__)


async def aggregate_daily_metrics(db: AsyncSession, date_str: str | None = None):
    """
    Compute and upsert daily metrics for all active sellers.
    Called by worker cron daily.
    """
    if not date_str:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")

    sellers_result = await db.execute(select(User.id))
    seller_ids = [row[0] for row in sellers_result.all()]

    for seller_id in seller_ids:
        try:
            await _compute_seller_day(db, seller_id, date_str)
        except Exception as e:
            logger.error(f"Aggregate metrics error seller={seller_id} date={date_str}: {e}")

    await db.commit()
    logger.info(f"Daily metrics aggregated for {len(seller_ids)} sellers, date={date_str}")


async def _compute_seller_day(db: AsyncSession, seller_id: int, date_str: str):
    """Compute metrics for one seller for one day."""
    # Check existing
    existing = await db.execute(
        select(DailySellerMetric)
        .where(DailySellerMetric.seller_id == seller_id, DailySellerMetric.date == date_str)
    )
    metric = existing.scalar_one_or_none()
    if not metric:
        metric = DailySellerMetric(seller_id=seller_id, date=date_str)
        db.add(metric)

    # Chats incoming
    chats = await db.execute(
        select(func.count(Conversation.id))
        .where(Conversation.seller_id == seller_id)
        .where(func.cast(Conversation.created_at, func.date.__class__) == date_str)
    )
    metric.chats_in = chats.scalar() or 0

    # Orders
    for status_val, attr in [
        (OrderStatus.PENDING, "orders_created"),
        (OrderStatus.PAID, "orders_paid"),
        (OrderStatus.CANCELLED, "orders_cancelled"),
    ]:
        cnt = await db.execute(
            select(func.count(Order.id))
            .where(Order.seller_id == seller_id)
            .where(Order.status == status_val)
            .where(func.to_char(Order.created_at, "YYYY-MM-DD") == date_str)
        )
        setattr(metric, attr, cnt.scalar() or 0)

    # Revenue paid
    rev = await db.execute(
        select(func.coalesce(func.sum(Order.total), 0))
        .where(Order.seller_id == seller_id)
        .where(Order.status == OrderStatus.PAID)
        .where(func.to_char(Order.created_at, "YYYY-MM-DD") == date_str)
    )
    metric.revenue_paid = float(rev.scalar() or 0)

    # Pending payment value
    pend = await db.execute(
        select(func.coalesce(func.sum(Order.total), 0))
        .where(Order.seller_id == seller_id)
        .where(Order.status == OrderStatus.PENDING)
        .where(func.to_char(Order.created_at, "YYYY-MM-DD") == date_str)
    )
    metric.pending_payment_value = float(pend.scalar() or 0)

    # Top products
    from models.order import OrderItem
    top = await db.execute(
        select(OrderItem.product_name, func.sum(OrderItem.quantity), func.sum(OrderItem.subtotal))
        .join(Order, OrderItem.order_id == Order.id)
        .where(Order.seller_id == seller_id)
        .where(func.to_char(Order.created_at, "YYYY-MM-DD") == date_str)
        .group_by(OrderItem.product_name)
        .order_by(func.sum(OrderItem.subtotal).desc())
        .limit(5)
    )
    metric.top_products_json = [
        {"name": name, "qty": int(qty or 0), "revenue": float(rev or 0)}
        for name, qty, rev in top.all()
    ]

    await db.flush()

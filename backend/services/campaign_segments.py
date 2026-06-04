"""
Campaign segment resolver.

Implements real segment queries to find target customers for campaigns.
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func, and_, exists
from sqlalchemy.ext.asyncio import AsyncSession

from models.crm import Customer, CustomerEvent
from models.order import Order, OrderStatus


async def get_segment_customers(
    db: AsyncSession,
    *,
    seller_id: int,
    segment: str,
    metadata: dict | None = None,
    limit: int = 200,
) -> list:
    """
    Return customers matching the given segment for a seller.
    Each result is a Customer ORM object.
    """
    metadata = metadata or {}

    if segment == "repeat_buyer":
        return await _segment_repeat_buyer(db, seller_id, limit)
    elif segment == "abandoned_payment":
        return await _segment_abandoned_payment(db, seller_id, limit)
    elif segment == "asked_not_ordered":
        return await _segment_asked_not_ordered(db, seller_id, limit)
    elif segment == "bought_category":
        category = metadata.get("category", "")
        return await _segment_bought_category(db, seller_id, category, limit)
    elif segment == "inactive_customer":
        return await _segment_inactive_customer(db, seller_id, limit)
    else:
        # Default: return recent customers with phone
        return await _segment_all_with_phone(db, seller_id, limit)


async def _segment_repeat_buyer(db: AsyncSession, seller_id: int, limit: int) -> list:
    """Customers with total_orders >= 2."""
    result = await db.execute(
        select(Customer)
        .where(Customer.seller_id == seller_id)
        .where(Customer.total_orders >= 2)
        .where(Customer.phone != "")
        .order_by(Customer.total_spent.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _segment_abandoned_payment(db: AsyncSession, seller_id: int, limit: int) -> list:
    """Customers who have at least one pending order."""
    result = await db.execute(
        select(Customer)
        .where(Customer.seller_id == seller_id)
        .where(Customer.phone != "")
        .where(
            exists(
                select(Order.id)
                .where(Order.seller_id == seller_id)
                .where(Order.customer_phone == Customer.phone)
                .where(Order.status == OrderStatus.PENDING)
            )
        )
        .order_by(Customer.last_seen_at.desc().nullslast())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _segment_asked_not_ordered(db: AsyncSession, seller_id: int, limit: int) -> list:
    """Customers who have chat events but total_orders == 0."""
    result = await db.execute(
        select(Customer)
        .where(Customer.seller_id == seller_id)
        .where(Customer.total_orders == 0)
        .where(Customer.phone != "")
        .where(
            exists(
                select(CustomerEvent.id)
                .where(CustomerEvent.seller_id == seller_id)
                .where(CustomerEvent.customer_id == Customer.id)
            )
        )
        .order_by(Customer.last_seen_at.desc().nullslast())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _segment_bought_category(db: AsyncSession, seller_id: int, category: str, limit: int) -> list:
    """Customers whose order items contain a matching category."""
    if not category:
        return []

    # Get all orders for this seller that are not cancelled
    orders_result = await db.execute(
        select(Order)
        .where(Order.seller_id == seller_id)
        .where(Order.status != OrderStatus.CANCELLED)
    )
    orders = orders_result.scalars().all()

    # Find customer phones that bought this category
    matching_phones = set()
    for order in orders:
        items = order.items if isinstance(order.items, list) else []
        for item in items:
            item_cat = str(item.get("kategori", "")).lower()
            item_name = str(item.get("nama", "")).lower()
            if category.lower() in item_cat or category.lower() in item_name:
                if order.customer_phone:
                    matching_phones.add(order.customer_phone)

    if not matching_phones:
        return []

    result = await db.execute(
        select(Customer)
        .where(Customer.seller_id == seller_id)
        .where(Customer.phone.in_(matching_phones))
        .limit(limit)
    )
    return list(result.scalars().all())


async def _segment_inactive_customer(db: AsyncSession, seller_id: int, limit: int) -> list:
    """Customers not seen in 30 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    result = await db.execute(
        select(Customer)
        .where(Customer.seller_id == seller_id)
        .where(Customer.phone != "")
        .where(Customer.last_seen_at < cutoff)
        .order_by(Customer.last_seen_at.asc().nullslast())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _segment_all_with_phone(db: AsyncSession, seller_id: int, limit: int) -> list:
    """All customers with phone number (fallback segment)."""
    result = await db.execute(
        select(Customer)
        .where(Customer.seller_id == seller_id)
        .where(Customer.phone != "")
        .order_by(Customer.last_seen_at.desc().nullslast(), Customer.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())

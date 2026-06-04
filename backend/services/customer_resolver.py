"""
Customer resolver for CRM memory.
"""
from datetime import datetime, timezone

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from models.crm import Customer, CustomerEvent


async def resolve_customer(
    db: AsyncSession,
    *,
    seller_id: int,
    phone: str = "",
    whatsapp_id: str = "",
    session_id: str = "",
    name: str = "Customer",
) -> tuple[Customer, bool]:
    query = select(Customer).where(Customer.seller_id == seller_id)
    predicates = []
    if phone:
        predicates.append(Customer.phone == phone)
    if whatsapp_id:
        predicates.append(Customer.whatsapp_id == whatsapp_id)
    if session_id:
        predicates.append(Customer.session_id == session_id)
    if predicates:
        result = await db.execute(query.where(or_(*predicates)).limit(1))
        customer = result.scalar_one_or_none()
        if customer:
            customer.name = name or customer.name
            customer.phone = phone or customer.phone
            customer.whatsapp_id = whatsapp_id or customer.whatsapp_id
            customer.session_id = session_id or customer.session_id
            customer.last_seen_at = datetime.now(timezone.utc)
            return customer, False

    if name and name != "Customer":
        result = await db.execute(
            select(Customer)
            .where(Customer.seller_id == seller_id)
            .where(Customer.name.ilike(name))
            .limit(1)
        )
        customer = result.scalar_one_or_none()
        if customer:
            customer.phone = phone or customer.phone
            customer.whatsapp_id = whatsapp_id or customer.whatsapp_id
            customer.session_id = session_id or customer.session_id
            customer.last_seen_at = datetime.now(timezone.utc)
            return customer, False

    customer = Customer(
        seller_id=seller_id,
        name=name or "Customer",
        phone=phone,
        whatsapp_id=whatsapp_id,
        session_id=session_id,
        last_seen_at=datetime.now(timezone.utc),
    )
    db.add(customer)
    await db.flush()
    return customer, True


async def record_customer_event(
    db: AsyncSession,
    *,
    seller_id: int,
    customer_id: int,
    event_type: str,
    title: str,
    data: dict | None = None,
    source: str = "system",
) -> CustomerEvent:
    event = CustomerEvent(
        seller_id=seller_id,
        customer_id=customer_id,
        event_type=event_type,
        title=title,
        data=data or {},
        source=source,
    )
    db.add(event)
    return event

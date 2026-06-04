"""
Customer CRM endpoints.
"""
import csv
from io import StringIO
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import get_db
from models.user import User
from models.crm import Customer, CustomerProfile, CustomerEvent
from api.routes_auth import get_current_user
from core.audit import record_audit

router = APIRouter()


class CustomerUpdateRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    tags: list[str] | None = None
    notes: str | None = None
    preferences: list[str] | None = None


@router.get("/")
async def list_customers(
    q: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Customer).where(Customer.seller_id == current_user.id)
    if q:
        like = f"%{q}%"
        query = query.where(or_(Customer.name.ilike(like), Customer.phone.ilike(like), Customer.email.ilike(like)))
    query = query.order_by(Customer.last_seen_at.desc().nullslast(), Customer.created_at.desc()).limit(100)
    result = await db.execute(query)
    return [
        {
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "email": c.email,
            "tags": c.tags or [],
            "total_orders": c.total_orders,
            "total_spent": c.total_spent,
            "last_seen_at": c.last_seen_at.isoformat() if c.last_seen_at else "",
            "created_at": c.created_at.isoformat() if c.created_at else "",
        }
        for c in result.scalars().all()
    ]


@router.get("/export/csv")
async def export_customers_csv(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Customer)
        .where(Customer.seller_id == current_user.id)
        .order_by(Customer.created_at.desc())
    )
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "phone", "email", "tags", "total_orders", "total_spent", "last_seen_at"])
    for customer in result.scalars().all():
        writer.writerow([
            customer.id,
            customer.name,
            customer.phone,
            customer.email,
            ",".join(customer.tags or []),
            customer.total_orders,
            customer.total_spent,
            customer.last_seen_at.isoformat() if customer.last_seen_at else "",
        ])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=jualin_customers.csv"},
    )


@router.get("/{customer_id}")
async def get_customer(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id).where(Customer.seller_id == current_user.id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")
    profile_result = await db.execute(select(CustomerProfile).where(CustomerProfile.customer_id == customer.id))
    profile = profile_result.scalar_one_or_none()
    return {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "email": customer.email,
        "whatsapp_id": customer.whatsapp_id,
        "tags": customer.tags or [],
        "total_orders": customer.total_orders,
        "total_spent": customer.total_spent,
        "last_seen_at": customer.last_seen_at.isoformat() if customer.last_seen_at else "",
        "profile": {
            "preferences": profile.preferences if profile else [],
            "budget_range": profile.budget_range if profile else "",
            "sizes": profile.sizes if profile else [],
            "address_book": profile.address_book if profile else [],
            "notes": profile.notes if profile else "",
            "sentiment": profile.sentiment if profile else "neutral",
        },
    }


@router.patch("/{customer_id}")
async def update_customer(
    customer_id: int,
    req: CustomerUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id).where(Customer.seller_id == current_user.id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")
    before = {"name": customer.name, "email": customer.email, "tags": customer.tags}
    if req.name is not None:
        customer.name = req.name
    if req.email is not None:
        customer.email = req.email
    if req.tags is not None:
        customer.tags = req.tags[:20]
    profile_result = await db.execute(select(CustomerProfile).where(CustomerProfile.customer_id == customer.id))
    profile = profile_result.scalar_one_or_none()
    if not profile:
        profile = CustomerProfile(customer_id=customer.id)
        db.add(profile)
    if req.notes is not None:
        profile.notes = req.notes
    if req.preferences is not None:
        profile.preferences = req.preferences[:20]
    customer.last_seen_at = customer.last_seen_at or datetime.now(timezone.utc)
    await record_audit(
        db,
        action="customer.updated",
        entity_type="customer",
        entity_id=customer.id,
        seller_id=current_user.id,
        actor_user_id=current_user.id,
        actor_type="seller",
        before=before,
        after={"name": customer.name, "email": customer.email, "tags": customer.tags},
    )
    await db.commit()
    return {"message": "Customer updated", "id": customer.id}


@router.get("/{customer_id}/timeline")
async def customer_timeline(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    customer_result = await db.execute(
        select(Customer).where(Customer.id == customer_id).where(Customer.seller_id == current_user.id)
    )
    if not customer_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")
    events_result = await db.execute(
        select(CustomerEvent)
        .where(CustomerEvent.customer_id == customer_id)
        .where(CustomerEvent.seller_id == current_user.id)
        .order_by(CustomerEvent.created_at.desc())
        .limit(100)
    )
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "title": e.title,
            "data": e.data or {},
            "source": e.source,
            "created_at": e.created_at.isoformat() if e.created_at else "",
        }
        for e in events_result.scalars().all()
    ]

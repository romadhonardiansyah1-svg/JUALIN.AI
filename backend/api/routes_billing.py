"""
Billing and usage endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.database import get_db
from models.user import User, UserRole
from models.billing import Plan, Subscription, UsageCounter
from api.routes_auth import get_current_user

router = APIRouter()
settings = get_settings()

DEFAULT_PLANS = [
    {"code": "free", "name": "Free", "price_monthly": 0, "limits": {"chat_month": 50, "products": 10, "whatsapp_channels": 0, "campaign_sends": 0}},
    {"code": "starter", "name": "Starter", "price_monthly": 99000, "limits": {"chat_month": 500, "products": 50, "whatsapp_channels": 1, "campaign_sends": 200}},
    {"code": "pro", "name": "Pro", "price_monthly": 299000, "limits": {"chat_month": 2000, "products": 200, "whatsapp_channels": 2, "campaign_sends": 1000}},
    {"code": "bisnis", "name": "Bisnis", "price_monthly": 799000, "limits": {"chat_month": 10000, "products": 999999, "whatsapp_channels": 5, "campaign_sends": 5000}},
]


@router.get("/plans")
async def list_plans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Plan).where(Plan.is_active == 1).order_by(Plan.price_monthly.asc()))
    plans = result.scalars().all()
    if not plans:
        return DEFAULT_PLANS
    return [
        {
            "code": p.code,
            "name": p.name,
            "price_monthly": p.price_monthly,
            "limits": p.limits or {},
        }
        for p in plans
    ]


@router.get("/usage")
async def get_usage(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UsageCounter)
        .where(UsageCounter.seller_id == current_user.id)
        .order_by(UsageCounter.metric.asc())
    )
    return [
        {
            "metric": u.metric,
            "period": u.period,
            "used": u.used,
            "limit": u.limit_value,
        }
        for u in result.scalars().all()
    ]


@router.post("/admin/reset-usage/{seller_id}")
async def reset_usage(
    seller_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not settings.ENABLE_BILLING:
        raise HTTPException(status_code=403, detail="Billing belum diaktifkan")
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Hanya admin")
    result = await db.execute(select(UsageCounter).where(UsageCounter.seller_id == seller_id))
    for counter in result.scalars().all():
        counter.used = 0
    await db.commit()
    return {"message": "Usage reset", "seller_id": seller_id}


class ChangePlanRequest(BaseModel):
    plan_code: str = Field(min_length=1, max_length=50)


class OverrideQuotaRequest(BaseModel):
    metric: str = Field(min_length=1, max_length=100)
    new_limit: int = Field(ge=0)


@router.post("/admin/sellers/{seller_id}/plan")
async def admin_change_plan(
    seller_id: int,
    req: ChangePlanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: change a seller's plan."""
    if not settings.ENABLE_BILLING:
        raise HTTPException(status_code=403, detail="Billing belum diaktifkan")
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Hanya admin")

    from models.user import UserTier
    try:
        new_tier = UserTier(req.plan_code)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Plan tidak valid: {req.plan_code}")

    seller_result = await db.execute(select(User).where(User.id == seller_id))
    seller = seller_result.scalar_one_or_none()
    if not seller:
        raise HTTPException(status_code=404, detail="Seller tidak ditemukan")

    old_tier = seller.tier.value
    seller.tier = new_tier

    # Upsert subscription record
    sub_result = await db.execute(
        select(Subscription).where(Subscription.seller_id == seller_id).limit(1)
    )
    sub = sub_result.scalar_one_or_none()
    if not sub:
        from datetime import datetime, timezone
        sub = Subscription(
            seller_id=seller_id,
            plan_code=req.plan_code,
            status="active",
            current_period_start=datetime.now(timezone.utc),
        )
        db.add(sub)
    else:
        sub.plan_code = req.plan_code
        sub.status = "active"

    await db.commit()
    return {"message": f"Plan changed from {old_tier} to {req.plan_code}", "seller_id": seller_id}


@router.post("/admin/sellers/{seller_id}/override-quota")
async def admin_override_quota(
    seller_id: int,
    req: OverrideQuotaRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: override a specific quota metric for a seller."""
    if not settings.ENABLE_BILLING:
        raise HTTPException(status_code=403, detail="Billing belum diaktifkan")
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Hanya admin")

    # Update subscription override_limits
    sub_result = await db.execute(
        select(Subscription).where(Subscription.seller_id == seller_id).limit(1)
    )
    sub = sub_result.scalar_one_or_none()
    if not sub:
        from datetime import datetime, timezone
        seller_result = await db.execute(select(User).where(User.id == seller_id))
        seller = seller_result.scalar_one_or_none()
        if not seller:
            raise HTTPException(status_code=404, detail="Seller tidak ditemukan")
        sub = Subscription(
            seller_id=seller_id,
            plan_code=seller.tier.value,
            status="active",
            current_period_start=datetime.now(timezone.utc),
            override_limits={req.metric: req.new_limit},
        )
        db.add(sub)
    else:
        overrides = sub.override_limits or {}
        overrides[req.metric] = req.new_limit
        sub.override_limits = overrides

    await db.commit()
    return {"message": f"Quota {req.metric} overridden to {req.new_limit}", "seller_id": seller_id}


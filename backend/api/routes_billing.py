"""
Billing and usage endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
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

"""
Trust profile endpoints — seller-facing and public-facing.
AI prompt harus mengambil trust profile untuk menjawab refund/shipping/support.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from models.database import get_db
from models.user import User
from models.trust_profile import StoreTrustProfile
from api.routes_auth import get_current_user

router = APIRouter()


class TrustProfileUpdateRequest(BaseModel):
    refund_policy: Optional[str] = None
    shipping_policy: Optional[str] = None
    support_hours: Optional[str] = None
    verified_phone: Optional[bool] = None
    payment_enabled: Optional[bool] = None
    testimonials_json: Optional[list] = None


@router.get("/trust-profile")
async def get_trust_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get trust profile for the current seller."""
    result = await db.execute(
        select(StoreTrustProfile).where(StoreTrustProfile.seller_id == current_user.id)
    )
    tp = result.scalar_one_or_none()

    if not tp:
        # Auto-create empty profile
        tp = StoreTrustProfile(seller_id=current_user.id)
        db.add(tp)
        await db.commit()
        await db.refresh(tp)

    return {
        "id": tp.id,
        "refund_policy": tp.refund_policy or "",
        "shipping_policy": tp.shipping_policy or "",
        "support_hours": tp.support_hours or "",
        "verified_phone": tp.verified_phone,
        "payment_enabled": tp.payment_enabled,
        "testimonials": tp.testimonials_json or [],
    }


@router.patch("/trust-profile")
async def update_trust_profile(
    req: TrustProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update trust profile fields."""
    result = await db.execute(
        select(StoreTrustProfile).where(StoreTrustProfile.seller_id == current_user.id)
    )
    tp = result.scalar_one_or_none()
    if not tp:
        tp = StoreTrustProfile(seller_id=current_user.id)
        db.add(tp)

    if req.refund_policy is not None:
        tp.refund_policy = req.refund_policy
    if req.shipping_policy is not None:
        tp.shipping_policy = req.shipping_policy
    if req.support_hours is not None:
        tp.support_hours = req.support_hours
    if req.verified_phone is not None:
        tp.verified_phone = req.verified_phone
    if req.payment_enabled is not None:
        tp.payment_enabled = req.payment_enabled
    if req.testimonials_json is not None:
        tp.testimonials_json = req.testimonials_json

    await db.commit()
    return {"message": "Trust profile updated"}


@router.get("/public/trust-profile/{slug}")
async def get_public_trust_profile(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """Public trust profile — no auth. Only for published stores."""
    from models.storefront import Storefront

    # Find seller
    seller_result = await db.execute(select(User).where(User.slug == slug))
    seller = seller_result.scalar_one_or_none()
    if not seller:
        raise HTTPException(status_code=404, detail="Toko tidak ditemukan")

    # Check storefront published
    sf_result = await db.execute(
        select(Storefront).where(Storefront.seller_id == seller.id)
    )
    sf = sf_result.scalar_one_or_none()
    if not sf or not sf.is_published:
        raise HTTPException(status_code=404, detail="Storefront belum dipublish")

    # Get trust profile
    tp_result = await db.execute(
        select(StoreTrustProfile).where(StoreTrustProfile.seller_id == seller.id)
    )
    tp = tp_result.scalar_one_or_none()

    if not tp:
        return {
            "store_name": seller.nama_toko,
            "has_trust_profile": False,
        }

    return {
        "store_name": seller.nama_toko,
        "has_trust_profile": True,
        "refund_policy": tp.refund_policy or "",
        "shipping_policy": tp.shipping_policy or "",
        "support_hours": tp.support_hours or "",
        "verified_phone": tp.verified_phone,
        "payment_enabled": tp.payment_enabled,
        "testimonials": tp.testimonials_json or [],
    }

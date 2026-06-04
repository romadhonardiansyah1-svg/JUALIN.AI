"""
Referral & Reseller endpoints.
V1: tracking + commission report; payout manual.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import uuid as uuid_module

from models.database import get_db
from models.user import User
from models.referral import ReferralCode, ReferralEvent, ResellerProfile, CommissionEvent
from api.routes_auth import get_current_user

router = APIRouter()


class ReferralCodeCreate(BaseModel):
    description: str = ""
    commission_percent: float = 5.0


@router.post("/codes")
async def create_referral_code(
    req: ReferralCodeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    code = f"{current_user.slug}-{uuid_module.uuid4().hex[:6]}".upper()
    rc = ReferralCode(
        seller_id=current_user.id,
        code=code,
        description=req.description,
        commission_percent=req.commission_percent,
    )
    db.add(rc)
    await db.commit()
    return {"code": code, "id": rc.id, "commission_percent": rc.commission_percent}


@router.get("/codes")
async def list_referral_codes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ReferralCode).where(ReferralCode.seller_id == current_user.id)
        .order_by(ReferralCode.created_at.desc())
    )
    return [
        {
            "id": r.id, "code": r.code, "description": r.description,
            "commission_percent": r.commission_percent, "is_active": r.is_active,
            "total_clicks": r.total_clicks, "total_conversions": r.total_conversions,
            "total_revenue": r.total_revenue,
        }
        for r in result.scalars().all()
    ]


@router.get("/summary")
async def referral_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    codes = await db.execute(
        select(func.count(ReferralCode.id)).where(ReferralCode.seller_id == current_user.id)
    )
    clicks = await db.execute(
        select(func.coalesce(func.sum(ReferralCode.total_clicks), 0))
        .where(ReferralCode.seller_id == current_user.id)
    )
    conversions = await db.execute(
        select(func.coalesce(func.sum(ReferralCode.total_conversions), 0))
        .where(ReferralCode.seller_id == current_user.id)
    )
    revenue = await db.execute(
        select(func.coalesce(func.sum(ReferralCode.total_revenue), 0))
        .where(ReferralCode.seller_id == current_user.id)
    )
    pending = await db.execute(
        select(func.coalesce(func.sum(CommissionEvent.amount), 0))
        .where(CommissionEvent.seller_id == current_user.id, CommissionEvent.status == "pending")
    )

    return {
        "total_codes": codes.scalar() or 0,
        "total_clicks": clicks.scalar() or 0,
        "total_conversions": conversions.scalar() or 0,
        "total_revenue": float(revenue.scalar() or 0),
        "pending_commission": float(pending.scalar() or 0),
    }


@router.post("/track")
async def track_referral(
    request: Request,
    code: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint: track referral click. No auth required."""
    if not code:
        raise HTTPException(status_code=400, detail="Code required")

    result = await db.execute(
        select(ReferralCode).where(ReferralCode.code == code, ReferralCode.is_active == True)
    )
    rc = result.scalar_one_or_none()
    if not rc:
        raise HTTPException(status_code=404, detail="Invalid referral code")

    ip = request.client.host if request.client else ""
    event = ReferralEvent(
        referral_code_id=rc.id, seller_id=rc.seller_id,
        event_type="click", ip_address=ip,
    )
    db.add(event)
    rc.total_clicks = (rc.total_clicks or 0) + 1
    await db.commit()
    return {"message": "Referral tracked", "seller_slug": ""}


@router.get("/resellers")
async def list_resellers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ResellerProfile).where(ResellerProfile.seller_id == current_user.id)
        .order_by(ResellerProfile.created_at.desc())
    )
    return [
        {
            "id": r.id, "name": r.name, "email": r.email, "phone": r.phone,
            "total_earned": r.total_earned, "status": r.status,
        }
        for r in result.scalars().all()
    ]


# ── Referral Growth Loop (Market Acceptance Sprint 7) ──

@router.get("/my-link")
async def get_my_referral_link(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get or auto-create the seller's referral link."""
    from config import get_settings
    settings = get_settings()

    result = await db.execute(
        select(ReferralCode).where(
            ReferralCode.seller_id == current_user.id,
            ReferralCode.is_active == True,
        ).order_by(ReferralCode.created_at.asc()).limit(1)
    )
    rc = result.scalar_one_or_none()

    if not rc:
        code = f"REF-{current_user.slug}-{uuid_module.uuid4().hex[:4]}".upper()
        rc = ReferralCode(
            seller_id=current_user.id,
            code=code,
            description="Referral link otomatis",
            commission_percent=5.0,
        )
        db.add(rc)
        await db.commit()
        await db.refresh(rc)

    register_url = f"{settings.FRONTEND_URL}/register?ref={rc.code}"

    return {
        "code": rc.code,
        "link": register_url,
        "total_clicks": rc.total_clicks,
        "total_conversions": rc.total_conversions,
        "copy_caption": (
            f"Hai! Aku pakai JUALIN.AI buat bantuin jualan online dan hasilnya mantap. "
            f"Daftar gratis pakai link ini: {register_url} 🚀"
        ),
    }


@router.get("/rewards")
async def list_rewards(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List referral rewards for the current seller."""
    from models.referral import ReferralReward

    result = await db.execute(
        select(ReferralReward).where(ReferralReward.seller_id == current_user.id)
        .order_by(ReferralReward.created_at.desc())
    )
    rewards = result.scalars().all()

    return [
        {
            "id": rw.id,
            "reward_type": rw.reward_type,
            "reward_value": rw.reward_value,
            "status": rw.status,
            "referred_seller_id": rw.referred_seller_id,
            "claimed_at": rw.claimed_at.isoformat() if rw.claimed_at else None,
            "created_at": rw.created_at.isoformat() if rw.created_at else "",
        }
        for rw in rewards
    ]


class ClaimRewardRequest(BaseModel):
    reward_id: int


@router.post("/claim")
async def claim_reward(
    req: ClaimRewardRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Claim a referral reward.
    Validasi: tidak bisa self-claim, referred seller harus sudah aktif.
    """
    from models.referral import ReferralReward
    from datetime import datetime, timezone

    result = await db.execute(
        select(ReferralReward).where(
            ReferralReward.id == req.reward_id,
            ReferralReward.seller_id == current_user.id,
        )
    )
    reward = result.scalar_one_or_none()
    if not reward:
        raise HTTPException(status_code=404, detail="Reward tidak ditemukan")

    if reward.status == "claimed":
        return {"message": "Reward sudah diklaim sebelumnya", "already_claimed": True}

    if reward.status != "approved":
        raise HTTPException(status_code=400, detail="Reward belum diapprove")

    # Self-claim prevention
    if reward.referred_seller_id == current_user.id:
        raise HTTPException(status_code=400, detail="Tidak bisa klaim referral diri sendiri")

    reward.status = "claimed"
    reward.claimed_at = datetime.now(timezone.utc)
    await db.commit()

    return {"message": "Reward berhasil diklaim!", "reward_type": reward.reward_type, "reward_value": reward.reward_value}

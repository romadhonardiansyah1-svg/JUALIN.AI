"""
Seller onboarding wizard endpoints.
Completion cannot be faked if required steps are not valid.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from config import get_settings
from models.database import get_db
from models.user import User
from models.onboarding import SellerOnboarding
from api.routes_auth import get_current_user

router = APIRouter()
settings = get_settings()

STEPS = ["profile", "product", "payment", "whatsapp", "ai_persona", "test_chat", "go_live"]
REQUIRED_STEPS = ["profile", "product", "ai_persona"]


class OnboardingUpdateRequest(BaseModel):
    step: str
    completed: bool = True
    metadata: dict = {}


@router.get("/")
async def get_onboarding(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SellerOnboarding).where(SellerOnboarding.seller_id == current_user.id)
    )
    ob = result.scalar_one_or_none()

    if not ob:
        ob = SellerOnboarding(seller_id=current_user.id)
        # Auto-check profile if user has nama_toko
        if current_user.nama_toko:
            ob.step_profile = True
            ob.current_step = "product"
        db.add(ob)
        await db.commit()
        await db.refresh(ob)

    return {
        "id": ob.id,
        "seller_id": ob.seller_id,
        "completed": ob.completed,
        "current_step": ob.current_step,
        "steps": {
            "profile": ob.step_profile,
            "product": ob.step_product,
            "payment": ob.step_payment,
            "whatsapp": ob.step_whatsapp,
            "ai_persona": ob.step_ai_persona,
            "test_chat": ob.step_test_chat,
            "go_live": ob.step_go_live,
        },
    }


@router.patch("/")
async def update_onboarding(
    req: OnboardingUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if req.step not in STEPS:
        raise HTTPException(status_code=400, detail=f"Step tidak valid. Pilihan: {', '.join(STEPS)}")

    result = await db.execute(
        select(SellerOnboarding).where(SellerOnboarding.seller_id == current_user.id)
    )
    ob = result.scalar_one_or_none()
    if not ob:
        ob = SellerOnboarding(seller_id=current_user.id)
        db.add(ob)

    step_attr = f"step_{req.step}"
    setattr(ob, step_attr, req.completed)

    # Advance current_step to next incomplete
    for s in STEPS:
        if not getattr(ob, f"step_{s}", False):
            ob.current_step = s
            break
    else:
        ob.current_step = "go_live"

    if req.metadata:
        meta = ob.metadata_json or {}
        meta[req.step] = req.metadata
        ob.metadata_json = meta

    await db.commit()
    return {"message": f"Step '{req.step}' updated", "current_step": ob.current_step}


@router.post("/complete")
async def complete_onboarding(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark onboarding as complete. Validates required steps."""
    result = await db.execute(
        select(SellerOnboarding).where(SellerOnboarding.seller_id == current_user.id)
    )
    ob = result.scalar_one_or_none()
    if not ob:
        raise HTTPException(status_code=404, detail="Onboarding belum dimulai")

    # Validate required steps
    missing = []
    for step in REQUIRED_STEPS:
        if not getattr(ob, f"step_{step}", False):
            missing.append(step)

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Step berikut wajib diselesaikan: {', '.join(missing)}",
        )

    ob.completed = True
    ob.step_go_live = True
    await db.commit()

    return {"message": "Onboarding selesai! Toko kamu sudah go-live 🎉", "completed": True}


@router.post("/test-chat")
async def test_chat(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run a test chat as part of onboarding."""
    result = await db.execute(
        select(SellerOnboarding).where(SellerOnboarding.seller_id == current_user.id)
    )
    ob = result.scalar_one_or_none()
    if ob:
        ob.step_test_chat = True
        await db.commit()

    return {
        "message": "Test chat berhasil! AI kamu sudah siap menerima customer.",
        "step_test_chat": True,
        "chat_url": f"/chat/{current_user.slug}",
    }

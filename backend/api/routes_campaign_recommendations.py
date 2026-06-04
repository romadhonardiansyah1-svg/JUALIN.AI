"""
AI Campaign autopilot recommendation endpoints.
Autopilot only recommends — seller must approve before sending.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.database import get_db
from models.user import User
from models.campaign_recommendation import CampaignRecommendation
from api.routes_auth import get_current_user

router = APIRouter()
settings = get_settings()


@router.get("/recommendations")
async def list_recommendations(
    status: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(CampaignRecommendation).where(
        CampaignRecommendation.seller_id == current_user.id
    )
    if status:
        query = query.where(CampaignRecommendation.status == status)
    query = query.order_by(CampaignRecommendation.created_at.desc()).limit(50)

    result = await db.execute(query)
    return [
        {
            "id": r.id,
            "trigger_type": r.trigger_type,
            "title": r.title,
            "description": r.description,
            "suggested_content": r.suggested_content,
            "estimated_reach": r.estimated_reach,
            "status": r.status,
            "campaign_id": r.campaign_id,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in result.scalars().all()
    ]


@router.post("/recommendations/{rec_id}/create-draft")
async def create_draft_from_recommendation(
    rec_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a campaign draft from a recommendation. Does NOT send."""
    result = await db.execute(
        select(CampaignRecommendation)
        .where(CampaignRecommendation.id == rec_id, CampaignRecommendation.seller_id == current_user.id)
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Rekomendasi tidak ditemukan")

    if rec.status == "draft_created" and rec.campaign_id:
        return {"message": "Draft sudah dibuat", "campaign_id": rec.campaign_id}

    # Create campaign draft
    from models.campaign import Campaign
    campaign = Campaign(
        seller_id=current_user.id,
        title=f"[Autopilot] {rec.title}",
        content=rec.suggested_content,
        status="draft",
    )
    db.add(campaign)
    await db.flush()

    rec.status = "draft_created"
    rec.campaign_id = campaign.id
    await db.commit()

    return {
        "message": "Draft campaign berhasil dibuat dari rekomendasi.",
        "campaign_id": campaign.id,
        "campaign_title": campaign.title,
    }


@router.post("/recommendations/{rec_id}/dismiss")
async def dismiss_recommendation(
    rec_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CampaignRecommendation)
        .where(CampaignRecommendation.id == rec_id, CampaignRecommendation.seller_id == current_user.id)
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Rekomendasi tidak ditemukan")

    rec.status = "dismissed"
    await db.commit()
    return {"message": "Rekomendasi dismissed"}

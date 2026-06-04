"""
Campaign generator endpoints.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.database import get_db
from models.user import User
from models.crm import Customer
from models.campaign import Campaign, CampaignRecipient, CampaignMessage
from api.routes_auth import get_current_user
from core.quota import check_usage_quota, increment_usage

router = APIRouter()
settings = get_settings()


class CampaignGenerateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    segment: str = "repeat_buyer"
    channel: str = "whatsapp"
    offer: str = ""


class CampaignUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    content: str | None = Field(default=None, min_length=1, max_length=2000)


def _campaign_copy(req: CampaignGenerateRequest, store_name: str) -> str:
    offer = req.offer or "promo terbaru"
    return (
        f"Halo kak, {store_name} punya {offer} khusus untuk kakak. "
        "Kalau mau, balas pesan ini ya, nanti kami bantu pilihkan produk yang paling cocok."
    )


@router.get("/")
async def list_campaigns(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign)
        .where(Campaign.seller_id == current_user.id)
        .order_by(Campaign.created_at.desc())
        .limit(50)
    )
    return [
        {
            "id": campaign.id,
            "title": campaign.title,
            "segment": campaign.segment,
            "channel": campaign.channel,
            "content": campaign.content,
            "status": campaign.status,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else "",
        }
        for campaign in result.scalars().all()
    ]


@router.post("/generate")
async def generate_campaign(
    req: CampaignGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not settings.ENABLE_CAMPAIGNS:
        raise HTTPException(status_code=403, detail="Campaign generator belum diaktifkan")
    campaign = Campaign(
        seller_id=current_user.id,
        title=req.title,
        segment=req.segment,
        channel=req.channel,
        content=_campaign_copy(req, current_user.nama_toko),
        status="draft",
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return {"id": campaign.id, "title": campaign.title, "content": campaign.content, "status": campaign.status}


@router.patch("/{campaign_id}")
async def update_campaign(
    campaign_id: int,
    req: CampaignUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id).where(Campaign.seller_id == current_user.id)
    )
    campaign = campaign_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign tidak ditemukan")
    if campaign.status in ("queued", "sending", "sent"):
        raise HTTPException(status_code=400, detail="Campaign yang sudah dikirim tidak bisa diedit")
    if req.title is not None:
        campaign.title = req.title
    if req.content is not None:
        campaign.content = req.content
    campaign.status = "draft"
    await db.commit()
    return {"id": campaign.id, "title": campaign.title, "content": campaign.content, "status": campaign.status}


@router.post("/{campaign_id}/preview")
async def preview_campaign(
    campaign_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id).where(Campaign.seller_id == current_user.id)
    )
    campaign = campaign_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign tidak ditemukan")

    customers_result = await db.execute(
        select(Customer)
        .where(Customer.seller_id == current_user.id)
        .order_by(Customer.last_seen_at.desc().nullslast(), Customer.created_at.desc())
        .limit(25)
    )
    existing_result = await db.execute(select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign.id))
    existing_customer_ids = {recipient.customer_id for recipient in existing_result.scalars().all() if recipient.customer_id}
    recipients = []
    for customer in customers_result.scalars().all():
        if not customer.phone or customer.id in existing_customer_ids:
            continue
        recipients.append(CampaignRecipient(
            campaign_id=campaign.id,
            customer_id=customer.id,
            name=customer.name,
            phone=customer.phone,
        ))
    if recipients:
        db.add_all(recipients)
    campaign.status = "previewed"
    await db.flush()
    total_result = await db.execute(select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign.id))
    total_recipients = len(total_result.scalars().all())
    await db.commit()
    return {
        "campaign_id": campaign.id,
        "status": campaign.status,
        "recipient_count": total_recipients,
        "content": campaign.content,
    }


@router.post("/{campaign_id}/send")
async def send_campaign(
    campaign_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id).where(Campaign.seller_id == current_user.id)
    )
    campaign = campaign_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign tidak ditemukan")
    if campaign.status != "previewed":
        raise HTTPException(status_code=400, detail="Preview campaign wajib dibuat sebelum send")

    recipients_result = await db.execute(select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign.id))
    recipients = recipients_result.scalars().all()
    if not recipients:
        raise HTTPException(status_code=400, detail="Tidak ada recipient untuk campaign ini")
    quota = await check_usage_quota(db, user=current_user, metric="campaign_sends", increment=len(recipients))
    if not quota["allowed"]:
        raise HTTPException(status_code=403, detail=f"Quota campaign tidak cukup. Sisa {quota['remaining']} dari limit {quota['limit']}.")
    for recipient in recipients:
        db.add(CampaignMessage(
            campaign_id=campaign.id,
            recipient_id=recipient.id,
            status="queued",
            content=campaign.content,
        ))
        recipient.status = "queued"
    await increment_usage(db, user=current_user, metric="campaign_sends", amount=len(recipients))
    campaign.status = "queued"
    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "Campaign queued", "campaign_id": campaign.id, "recipient_count": len(recipients)}

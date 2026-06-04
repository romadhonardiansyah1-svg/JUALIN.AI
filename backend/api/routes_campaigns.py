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
    campaigns = result.scalars().all()
    # Batch load recipient/message counts
    campaign_ids = [c.id for c in campaigns]
    stats_map = {}
    if campaign_ids:
        from sqlalchemy import func
        msg_result = await db.execute(
            select(
                CampaignMessage.campaign_id,
                func.count(CampaignMessage.id).label("total"),
                func.count(CampaignMessage.id).filter(CampaignMessage.status == "sent").label("sent"),
                func.count(CampaignMessage.id).filter(CampaignMessage.status == "failed").label("failed"),
            )
            .where(CampaignMessage.campaign_id.in_(campaign_ids))
            .group_by(CampaignMessage.campaign_id)
        )
        for row in msg_result.all():
            stats_map[row[0]] = {"total": row[1], "sent": row[2], "failed": row[3]}
        recip_result = await db.execute(
            select(
                CampaignRecipient.campaign_id,
                func.count(CampaignRecipient.id).label("count"),
            )
            .where(CampaignRecipient.campaign_id.in_(campaign_ids))
            .group_by(CampaignRecipient.campaign_id)
        )
        for row in recip_result.all():
            if row[0] not in stats_map:
                stats_map[row[0]] = {"total": 0, "sent": 0, "failed": 0}
            stats_map[row[0]]["recipients"] = row[1]

    return [
        {
            "id": campaign.id,
            "title": campaign.title,
            "segment": campaign.segment,
            "channel": campaign.channel,
            "content": campaign.content,
            "status": campaign.status,
            "recipient_count": stats_map.get(campaign.id, {}).get("recipients", 0),
            "sent_count": stats_map.get(campaign.id, {}).get("sent", 0),
            "failed_count": stats_map.get(campaign.id, {}).get("failed", 0),
            "created_at": campaign.created_at.isoformat() if campaign.created_at else "",
        }
        for campaign in campaigns
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

    from services.campaign_segments import get_segment_customers

    # Use real segment service
    segment_customers = await get_segment_customers(
        db,
        seller_id=current_user.id,
        segment=campaign.segment,
        metadata=campaign.metadata_json,
        limit=200,
    )

    # Clear stale recipients if content/segment changed
    if campaign.status == "draft":
        existing_result = await db.execute(
            select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign.id)
        )
        for old in existing_result.scalars().all():
            await db.delete(old)
        await db.flush()

    existing_result = await db.execute(select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign.id))
    existing_customer_ids = {r.customer_id for r in existing_result.scalars().all() if r.customer_id}

    recipients = []
    for customer in segment_customers:
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
        "segment": campaign.segment,
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
    from core.idempotency import enqueue_job_record

    for recipient in recipients:
        cm = CampaignMessage(
            campaign_id=campaign.id,
            recipient_id=recipient.id,
            status="queued",
            content=campaign.content,
        )
        db.add(cm)
        recipient.status = "queued"
    await db.flush()

    # Enqueue as background jobs
    msg_result = await db.execute(
        select(CampaignMessage)
        .where(CampaignMessage.campaign_id == campaign.id)
        .where(CampaignMessage.status == "queued")
    )
    for cm in msg_result.scalars().all():
        await enqueue_job_record(
            db,
            job_type="campaign_send_message",
            seller_id=current_user.id,
            payload={"campaign_message_id": cm.id},
            idempotency_key=f"campaign_send_message:{cm.id}",
        )

    await increment_usage(db, user=current_user, metric="campaign_sends", amount=len(recipients))
    campaign.status = "queued"
    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "Campaign queued", "campaign_id": campaign.id, "recipient_count": len(recipients)}

"""
Integration setup endpoints.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.database import get_db
from models.user import User
from models.scale_core import IntegrationAccount
from models.inbox import Channel
from api.routes_auth import get_current_user
from core.secure_config import encrypt_config, decrypt_config, redact_config
from core.audit import record_audit
from services.messaging.whatsapp_cloud import WhatsAppCloudProvider

router = APIRouter()
settings = get_settings()


class WhatsAppConnectRequest(BaseModel):
    phone_number_id: str = Field(min_length=3, max_length=255)
    access_token: str = Field(min_length=10)
    display_name: str = "WhatsApp"
    app_secret: str = ""


@router.post("/whatsapp/connect")
async def connect_whatsapp(
    req: WhatsAppConnectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not settings.ENABLE_WHATSAPP:
        raise HTTPException(status_code=403, detail="WhatsApp integration belum diaktifkan")

    config = {
        "phone_number_id": req.phone_number_id,
        "access_token": req.access_token,
        "app_secret": req.app_secret,
    }

    result = await db.execute(
        select(IntegrationAccount)
        .where(IntegrationAccount.seller_id == current_user.id)
        .where(IntegrationAccount.provider_type == "messaging")
        .where(IntegrationAccount.provider == "whatsapp_cloud")
    )
    integration = result.scalar_one_or_none()
    if integration:
        before = redact_config(decrypt_config(integration.config_encrypted))
        integration.display_name = req.display_name
        integration.status = "active"
        integration.config_encrypted = encrypt_config(config)
        integration.capabilities = ["send_message", "send_media", "webhook"]
    else:
        before = {}
        integration = IntegrationAccount(
            seller_id=current_user.id,
            provider_type="messaging",
            provider="whatsapp_cloud",
            display_name=req.display_name,
            status="active",
            config_encrypted=encrypt_config(config),
            capabilities=["send_message", "send_media", "webhook"],
        )
        db.add(integration)

    channel_result = await db.execute(
        select(Channel)
        .where(Channel.seller_id == current_user.id)
        .where(Channel.type == "whatsapp")
        .where(Channel.provider == "whatsapp_cloud")
        .where(Channel.external_id == req.phone_number_id)
    )
    channel = channel_result.scalar_one_or_none()
    if not channel:
        channel = Channel(
            seller_id=current_user.id,
            type="whatsapp",
            provider="whatsapp_cloud",
            external_id=req.phone_number_id,
            display_name=req.display_name,
            status="active",
            config_encrypted=encrypt_config(config),
        )
        db.add(channel)
    else:
        channel.display_name = req.display_name
        channel.status = "active"
        channel.config_encrypted = encrypt_config(config)

    await db.flush()
    await record_audit(
        db,
        action="integration.whatsapp.connect",
        entity_type="integration_account",
        entity_id=integration.id,
        seller_id=current_user.id,
        actor_user_id=current_user.id,
        actor_type="seller",
        before=before,
        after=redact_config(config),
    )
    await db.commit()

    return {
        "message": "WhatsApp integration connected",
        "provider": "whatsapp_cloud",
        "status": "active",
        "display_name": req.display_name,
        "phone_number_id": req.phone_number_id,
    }


@router.get("/")
async def list_integrations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(IntegrationAccount)
        .where(IntegrationAccount.seller_id == current_user.id)
        .order_by(IntegrationAccount.created_at.desc())
    )
    integrations = result.scalars().all()
    return [
        {
            "id": i.id,
            "provider_type": i.provider_type,
            "provider": i.provider,
            "status": i.status,
            "display_name": i.display_name,
            "capabilities": i.capabilities or [],
            "last_health_status": i.last_health_status,
            "created_at": i.created_at.isoformat() if i.created_at else "",
        }
        for i in integrations
    ]


@router.get("/health")
async def provider_health_check(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(IntegrationAccount)
        .where(IntegrationAccount.seller_id == current_user.id)
        .order_by(IntegrationAccount.provider_type.asc(), IntegrationAccount.provider.asc())
    )
    checks = []
    for integration in result.scalars().all():
        healthy = False
        detail = ""
        if integration.provider == "whatsapp_cloud":
            config = decrypt_config(integration.config_encrypted)
            health = await WhatsAppCloudProvider(
                access_token=config.get("access_token", ""),
                phone_number_id=config.get("phone_number_id", ""),
                app_secret=config.get("app_secret", ""),
            ).health_check()
            healthy = bool(health.get("configured"))
            detail = "configured" if healthy else "missing credentials"
        else:
            detail = "health check belum tersedia"
        integration.last_health_status = "healthy" if healthy else "unhealthy"
        integration.last_health_at = datetime.now(timezone.utc)
        checks.append({
            "provider_type": integration.provider_type,
            "provider": integration.provider,
            "status": integration.status,
            "healthy": healthy,
            "detail": detail,
        })
    await db.commit()
    return checks

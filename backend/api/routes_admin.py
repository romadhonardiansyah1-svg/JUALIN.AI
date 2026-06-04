"""
JUALIN.AI — Admin API Routes
Platform-level management for admin users
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from config import get_settings
from models.database import get_db
from models.user import User, UserRole, UserTier
from models.product import Product
from models.conversation import Conversation, Message
from models.order import Order, OrderStatus
from api.routes_auth import get_current_user

router = APIRouter()
settings = get_settings()


# ── Auth Guard ──

async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require admin role for access."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Akses ditolak. Hanya admin yang bisa mengakses halaman ini.")
    return current_user


# ── Pydantic Schemas ──

class SellerUpdateRequest(BaseModel):
    tier: Optional[str] = None
    ai_active: Optional[bool] = None
    suspended: Optional[bool] = None  # Not in DB yet, but for future


# ── Endpoints ──

@router.get("/stats")
async def get_platform_stats(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get platform-wide statistics for admin dashboard."""
    # Total sellers
    total_sellers = await db.execute(
        select(func.count(User.id)).where(User.role == UserRole.SELLER)
    )
    
    # Total products
    total_products = await db.execute(
        select(func.count(Product.id)).where(Product.is_active == 1)
    )
    
    # Total orders
    total_orders = await db.execute(select(func.count(Order.id)))
    
    # Total revenue
    total_revenue = await db.execute(
        select(func.coalesce(func.sum(Order.total), 0))
        .where(Order.status != OrderStatus.CANCELLED)
    )
    
    # Total conversations
    total_chats = await db.execute(select(func.count(Conversation.id)))
    
    # Active sellers today (had conversations today)
    today = datetime.now(timezone.utc).date()
    active_today = await db.execute(
        select(func.count(func.distinct(Conversation.seller_id)))
        .where(func.date(Conversation.created_at) == today)
    )
    
    # Total messages
    total_messages = await db.execute(select(func.count(Message.id)))
    
    # Pending orders
    pending_orders = await db.execute(
        select(func.count(Order.id))
        .where(Order.status == OrderStatus.PENDING)
    )
    
    return {
        "total_sellers": total_sellers.scalar() or 0,
        "total_products": total_products.scalar() or 0,
        "total_orders": total_orders.scalar() or 0,
        "total_revenue": total_revenue.scalar() or 0,
        "total_chats": total_chats.scalar() or 0,
        "active_today": active_today.scalar() or 0,
        "total_messages": total_messages.scalar() or 0,
        "pending_orders": pending_orders.scalar() or 0,
    }


@router.get("/sellers")
async def list_sellers(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all sellers with their stats (optimized: batch queries instead of N+1)."""
    # 1. Get all sellers
    result = await db.execute(
        select(User)
        .where(User.role == UserRole.SELLER)
        .order_by(User.created_at.desc())
    )
    sellers = result.scalars().all()
    seller_ids = [s.id for s in sellers]
    
    if not seller_ids:
        return []
    
    # 2. Batch: product counts per seller (BUG 13 FIX)
    prod_result = await db.execute(
        select(Product.seller_id, func.count(Product.id))
        .where(Product.seller_id.in_(seller_ids))
        .where(Product.is_active == 1)
        .group_by(Product.seller_id)
    )
    prod_map = dict(prod_result.all())
    
    # 3. Batch: order counts + revenue per seller
    order_result = await db.execute(
        select(
            Order.seller_id,
            func.count(Order.id),
            func.coalesce(func.sum(Order.total), 0),
        )
        .where(Order.seller_id.in_(seller_ids))
        .where(Order.status != OrderStatus.CANCELLED)
        .group_by(Order.seller_id)
    )
    order_map = {}
    revenue_map = {}
    for row in order_result.all():
        order_map[row[0]] = row[1]
        revenue_map[row[0]] = row[2]
    
    # 4. Batch: chat counts per seller
    chat_result = await db.execute(
        select(Conversation.seller_id, func.count(Conversation.id))
        .where(Conversation.seller_id.in_(seller_ids))
        .group_by(Conversation.seller_id)
    )
    chat_map = dict(chat_result.all())
    
    # 5. Build response
    return [
        {
            "id": s.id,
            "nama_toko": s.nama_toko,
            "email": s.email,
            "slug": s.slug,
            "tier": s.tier.value,
            "ai_active": s.ai_active,
            "ai_style": s.ai_style,
            "no_hp": s.no_hp or "",
            "products": prod_map.get(s.id, 0),
            "orders": order_map.get(s.id, 0),
            "revenue": revenue_map.get(s.id, 0),
            "chats": chat_map.get(s.id, 0),
            "created_at": s.created_at.isoformat() if s.created_at else "",
            "status": "active" if s.ai_active else "inactive",
        }
        for s in sellers
    ]


@router.patch("/sellers/{seller_id}")
async def update_seller(
    seller_id: int,
    req: SellerUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin update seller: change tier, toggle AI, etc."""
    result = await db.execute(
        select(User)
        .where(User.id == seller_id)
        .where(User.role == UserRole.SELLER)
    )
    seller = result.scalar_one_or_none()
    
    if not seller:
        raise HTTPException(status_code=404, detail="Seller tidak ditemukan")
    
    if req.tier is not None:
        try:
            seller.tier = UserTier(req.tier)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Tier tidak valid: {req.tier}")
    
    if req.ai_active is not None:
        seller.ai_active = req.ai_active
    
    await db.commit()
    await db.refresh(seller)
    
    return {
        "message": f"Seller {seller.nama_toko} berhasil diupdate",
        "id": seller.id,
        "tier": seller.tier.value,
        "ai_active": seller.ai_active,
    }


@router.get("/system")
async def get_system_health(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get system health information."""
    import platform
    import sys
    
    database_status = "disconnected"
    try:
        await db.execute(text("SELECT 1"))
        database_status = "connected"
    except Exception:
        pass

    # Check Redis
    redis_status = "disconnected"
    try:
        from cache import get_redis
        r = await get_redis()
        if r:
            await r.ping()
            redis_status = "connected"
    except Exception:
        pass
    
    return {
        "backend": "online",
        "database": database_status,
        "redis": redis_status,
        "ai_engine": "ready",
        "followup_scheduler": "running" if settings.SCHEDULER_ENABLED else "disabled",
        "version": settings.APP_VERSION,
        "python_version": sys.version.split()[0],
        "platform": platform.system(),
        "llm_model": settings.LLM_MODEL,
        "embedding_model": settings.EMBEDDING_MODEL,
    }


@router.get("/provider-health")
async def get_provider_health(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get provider health status for admin dashboard."""
    providers = {}

    # 1. Database
    try:
        await db.execute(text("SELECT 1"))
        providers["database"] = {"status": "alive", "provider": "PostgreSQL"}
    except Exception:
        providers["database"] = {"status": "offline", "provider": "PostgreSQL"}

    # 2. Redis
    try:
        from cache import get_redis
        r = await get_redis()
        if r:
            await r.ping()
            providers["redis"] = {"status": "alive", "provider": "Redis"}
        else:
            providers["redis"] = {"status": "offline", "provider": "Redis"}
    except Exception:
        providers["redis"] = {"status": "offline", "provider": "Redis"}

    # 3. Worker (via heartbeat)
    try:
        from models.system_heartbeat import SystemHeartbeat
        hb_result = await db.execute(
            select(SystemHeartbeat).where(SystemHeartbeat.service == "worker")
        )
        hb = hb_result.scalar_one_or_none()
        if hb and hb.last_seen_at:
            last_seen = hb.last_seen_at
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=datetime.now(timezone.utc).tzinfo)
            age_seconds = (datetime.now(timezone.utc) - last_seen).total_seconds()
            if age_seconds < 90:
                providers["worker"] = {"status": "alive", "last_seen": hb.last_seen_at.isoformat()}
            elif age_seconds < 300:
                providers["worker"] = {"status": "degraded", "last_seen": hb.last_seen_at.isoformat()}
            else:
                providers["worker"] = {"status": "offline", "last_seen": hb.last_seen_at.isoformat()}
        else:
            providers["worker"] = {"status": "unknown", "last_seen": None}
    except Exception:
        providers["worker"] = {"status": "unknown"}

    # 4. WhatsApp
    if settings.ENABLE_WHATSAPP:
        providers["whatsapp"] = {
            "status": "configured" if settings.WHATSAPP_ACCESS_TOKEN else "not_configured",
            "provider": "WhatsApp Cloud API",
        }
    else:
        providers["whatsapp"] = {"status": "disabled"}

    # 5. Payment
    providers["payment"] = {
        "midtrans": "configured" if settings.MIDTRANS_SERVER_KEY else "missing_config",
        "cashi": "configured" if settings.CASHI_API_KEY else "missing_config",
    }

    # 6. LLM
    providers["llm"] = {
        "status": "configured",
        "provider": settings.LLM_MODEL,
        "base_url_set": bool(settings.LLM_BASE_URL),
    }

    return providers


# ══════════════════════════════════════════════════
# Jobs Management
# ══════════════════════════════════════════════════

@router.get("/jobs")
async def list_jobs(
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List background jobs with optional filters."""
    from models.scale_core import BackgroundJob

    query = select(BackgroundJob).order_by(BackgroundJob.created_at.desc())
    if status:
        query = query.where(BackgroundJob.status == status)
    if job_type:
        query = query.where(BackgroundJob.job_type == job_type)
    query = query.limit(min(limit, 200)).offset(offset)

    result = await db.execute(query)
    jobs = result.scalars().all()

    # Count totals by status
    count_result = await db.execute(
        select(BackgroundJob.status, func.count(BackgroundJob.id))
        .group_by(BackgroundJob.status)
    )
    status_counts = {row[0]: row[1] for row in count_result.all()}

    return {
        "jobs": [
            {
                "id": j.id,
                "job_type": j.job_type,
                "status": j.status,
                "seller_id": j.seller_id,
                "attempts": j.attempts,
                "max_attempts": j.max_attempts,
                "retryable": j.retryable,
                "error_message": j.error_message[:500] if j.error_message else "",
                "last_error_code": j.last_error_code,
                "created_at": j.created_at.isoformat() if j.created_at else "",
                "started_at": j.started_at.isoformat() if j.started_at else "",
                "finished_at": j.finished_at.isoformat() if j.finished_at else "",
            }
            for j in jobs
        ],
        "status_counts": status_counts,
        "limit": limit,
        "offset": offset,
    }


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Re-enqueue a failed/dead_letter job for retry."""
    from models.scale_core import BackgroundJob
    from core.audit import record_audit

    result = await db.execute(select(BackgroundJob).where(BackgroundJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("failed", "dead_letter"):
        raise HTTPException(status_code=400, detail=f"Cannot retry job with status '{job.status}'")

    old_status = job.status
    job.status = "queued"
    job.max_attempts = job.attempts + 3
    job.retryable = True
    job.error_message = ""
    job.last_error_code = ""
    job.locked_at = None
    job.locked_by = ""
    job.finished_at = None

    await record_audit(
        db, action="admin.job.retry", entity_type="background_job", entity_id=job_id,
        actor_user_id=admin.id, actor_type="admin",
        before={"status": old_status}, after={"status": "queued"},
    )
    await db.commit()

    return {"message": "Job re-queued", "job_id": job.id, "new_status": "queued"}


@router.post("/webhooks/{event_id}/replay")
async def replay_webhook(
    event_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Replay a webhook event by resetting its status."""
    from models.scale_core import WebhookEvent
    from core.audit import record_audit

    result = await db.execute(select(WebhookEvent).where(WebhookEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Webhook event not found")

    old_status = event.status
    event.status = "received"
    event.processed_at = None
    event.error_message = ""

    await record_audit(
        db, action="admin.webhook.replay", entity_type="webhook_event", entity_id=event_id,
        actor_user_id=admin.id, actor_type="admin",
        before={"status": old_status}, after={"status": "received"},
    )
    await db.commit()

    return {"message": "Webhook event reset for replay", "event_id": event.id}


@router.get("/audit-logs")
async def list_audit_logs(
    seller_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Browse audit logs with filters."""
    from models.scale_core import AuditLog

    query = select(AuditLog).order_by(AuditLog.created_at.desc())
    if seller_id:
        query = query.where(AuditLog.seller_id == seller_id)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if action:
        query = query.where(AuditLog.action == action)
    query = query.limit(min(limit, 200)).offset(offset)

    result = await db.execute(query)
    logs = result.scalars().all()

    return [
        {
            "id": log.id,
            "seller_id": log.seller_id,
            "actor_user_id": log.actor_user_id,
            "actor_type": log.actor_type,
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "before": log.before,
            "after": log.after,
            "created_at": log.created_at.isoformat() if log.created_at else "",
        }
        for log in logs
    ]


# ── Concierge Setup Mode (Market Acceptance Sprint 8) ──

class SetupChecklistUpdate(BaseModel):
    products_imported: Optional[bool] = None
    whatsapp_connected: Optional[bool] = None
    payment_connected: Optional[bool] = None
    storefront_published: Optional[bool] = None
    first_campaign_draft: Optional[bool] = None
    notes: Optional[str] = None


@router.post("/sellers/{seller_id}/concierge-start")
async def start_concierge(
    seller_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Start concierge mode for a seller. Creates setup checklist. Audit logged."""
    from models.concierge_checklist import ConciergeChecklist
    from core.audit import record_audit

    # Check seller exists
    seller_result = await db.execute(select(User).where(User.id == seller_id))
    seller = seller_result.scalar_one_or_none()
    if not seller:
        raise HTTPException(status_code=404, detail="Seller tidak ditemukan")

    # Check if already started
    existing = await db.execute(
        select(ConciergeChecklist).where(ConciergeChecklist.seller_id == seller_id)
    )
    checklist = existing.scalar_one_or_none()
    if checklist:
        return {
            "message": "Concierge sudah dimulai sebelumnya",
            "checklist_id": checklist.id,
            "already_started": True,
        }

    checklist = ConciergeChecklist(
        seller_id=seller_id,
        admin_id=admin.id,
    )
    db.add(checklist)

    await record_audit(
        db, action="concierge_start", entity_type="seller",
        entity_id=seller_id, seller_id=seller_id,
        actor_user_id=admin.id, actor_type="admin",
        metadata={"admin_email": admin.email},
    )

    await db.commit()
    return {"message": "Concierge mode dimulai", "checklist_id": checklist.id}


@router.patch("/sellers/{seller_id}/setup-checklist")
async def update_setup_checklist(
    seller_id: int,
    req: SetupChecklistUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update concierge setup checklist items."""
    from models.concierge_checklist import ConciergeChecklist

    result = await db.execute(
        select(ConciergeChecklist).where(ConciergeChecklist.seller_id == seller_id)
    )
    checklist = result.scalar_one_or_none()
    if not checklist:
        raise HTTPException(status_code=404, detail="Checklist tidak ditemukan. Mulai concierge dulu.")

    if req.products_imported is not None:
        checklist.products_imported = req.products_imported
    if req.whatsapp_connected is not None:
        checklist.whatsapp_connected = req.whatsapp_connected
    if req.payment_connected is not None:
        checklist.payment_connected = req.payment_connected
    if req.storefront_published is not None:
        checklist.storefront_published = req.storefront_published
    if req.first_campaign_draft is not None:
        checklist.first_campaign_draft = req.first_campaign_draft
    if req.notes is not None:
        checklist.notes = req.notes

    # Auto-complete if all items checked
    all_done = all([
        checklist.products_imported, checklist.whatsapp_connected,
        checklist.payment_connected, checklist.storefront_published,
        checklist.first_campaign_draft,
    ])
    if all_done and not checklist.completed_at:
        checklist.completed_at = datetime.now(timezone.utc)

    await db.commit()

    return {
        "message": "Checklist updated",
        "completed": all_done,
        "checklist": {
            "products_imported": checklist.products_imported,
            "whatsapp_connected": checklist.whatsapp_connected,
            "payment_connected": checklist.payment_connected,
            "storefront_published": checklist.storefront_published,
            "first_campaign_draft": checklist.first_campaign_draft,
            "notes": checklist.notes,
            "completed_at": checklist.completed_at.isoformat() if checklist.completed_at else None,
        },
    }


@router.post("/sellers/{seller_id}/impersonation-token")
async def create_impersonation_token(
    seller_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a short-lived JWT for impersonation. 15min default.
    All actions are audit-logged with impersonation=true.
    """
    import jwt as pyjwt
    from core.audit import record_audit

    seller_result = await db.execute(select(User).where(User.id == seller_id))
    seller = seller_result.scalar_one_or_none()
    if not seller:
        raise HTTPException(status_code=404, detail="Seller tidak ditemukan")

    # Generate impersonation token
    from datetime import timedelta
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.IMPERSONATION_TOKEN_MINUTES)

    payload = {
        "sub": str(seller.id),
        "email": seller.email,
        "role": seller.role.value if hasattr(seller.role, 'value') else seller.role,
        "impersonation": True,
        "impersonated_by": admin.id,
        "target_seller_id": seller.id,
        "exp": exp,
    }
    token = pyjwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    # Audit log
    await record_audit(
        db, action="impersonation_token_created", entity_type="seller",
        entity_id=seller_id, seller_id=seller_id,
        actor_user_id=admin.id, actor_type="admin",
        metadata={
            "admin_email": admin.email,
            "target_seller_email": seller.email,
            "expires_at": exp.isoformat(),
            "duration_minutes": settings.IMPERSONATION_TOKEN_MINUTES,
        },
    )
    await db.commit()

    return {
        "token": token,
        "seller_name": seller.nama_toko,
        "seller_email": seller.email,
        "expires_at": exp.isoformat(),
        "duration_minutes": settings.IMPERSONATION_TOKEN_MINUTES,
        "message": f"Token impersonasi untuk {seller.nama_toko} berlaku {settings.IMPERSONATION_TOKEN_MINUTES} menit",
    }

"""
JUALIN.AI — Admin API Routes
Platform-level management for admin users
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
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
    result = await db.execute(select(User).where(User.id == seller_id))
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
):
    """Get system health information."""
    import platform
    import sys
    
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
        "database": "connected",
        "redis": redis_status,
        "ai_engine": "ready",
        "followup_scheduler": "running",
        "version": settings.APP_VERSION,
        "python_version": sys.version.split()[0],
        "platform": platform.system(),
        "llm_model": settings.LLM_MODEL,
        "embedding_model": settings.EMBEDDING_MODEL,
    }

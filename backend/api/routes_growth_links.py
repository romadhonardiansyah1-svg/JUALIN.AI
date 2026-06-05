"""
Growth links endpoints — trackable links for WhatsApp, storefront, campaigns.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import uuid as uuid_module
from urllib.parse import urlparse

from config import get_settings
from models.database import get_db
from models.user import User
from models.growth_link import GrowthLink
from api.routes_auth import get_current_user

router = APIRouter()
settings = get_settings()

ALLOWED_EXTERNAL_REDIRECT_HOSTS = {
    "wa.me",
    "api.whatsapp.com",
    "web.whatsapp.com",
    "www.whatsapp.com",
}
ALLOWED_RELATIVE_REDIRECT_PREFIXES = ("/chat/", "/pay/")
ALLOWED_RELATIVE_REDIRECT_PATHS = {"/register"}


class GrowthLinkCreateRequest(BaseModel):
    source: str = Field(default="manual", max_length=50)
    campaign_name: str = Field(default="", max_length=120)
    target_url: str = Field(default="", max_length=2048)


def _configured_hosts() -> set[str]:
    hosts: set[str] = set()
    for base_url in (settings.FRONTEND_URL, settings.BASE_URL):
        parsed = urlparse(base_url)
        if parsed.hostname:
            hosts.add(parsed.hostname.lower())
    return hosts


def _is_allowed_public_path(path: str) -> bool:
    return path in ALLOWED_RELATIVE_REDIRECT_PATHS or path.startswith(ALLOWED_RELATIVE_REDIRECT_PREFIXES)


def _validate_redirect_target(target_url: str) -> str:
    """Restrict growth links to WhatsApp or this platform to prevent open redirect abuse."""
    target_url = (target_url or "").strip()
    if not target_url:
        raise HTTPException(status_code=400, detail="Target URL wajib diisi")

    if target_url.startswith("//"):
        raise HTTPException(status_code=400, detail="Target URL tidak valid")

    if target_url.startswith("/"):
        if _is_allowed_public_path(urlparse(target_url).path):
            return target_url
        raise HTTPException(status_code=400, detail="Target URL internal tidak diizinkan")

    parsed = urlparse(target_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Target URL harus memakai http/https yang valid")

    host = parsed.hostname.lower()
    if host in _configured_hosts() and _is_allowed_public_path(parsed.path):
        return target_url

    if parsed.scheme == "https" and host in ALLOWED_EXTERNAL_REDIRECT_HOSTS:
        return target_url

    raise HTTPException(status_code=400, detail="Target URL hanya boleh menuju WhatsApp atau domain JUALIN.AI")


@router.post("/")
async def create_growth_link(
    req: GrowthLinkCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new trackable growth link."""
    code = f"gl-{uuid_module.uuid4().hex[:8]}"

    # Default target URL based on source
    target_url = req.target_url
    if not target_url:
        if req.source == "wa_link":
            phone = (current_user.no_hp or "").replace("-", "").replace(" ", "")
            if phone.startswith("0"):
                phone = "62" + phone[1:]
            target_url = f"https://wa.me/{phone}?text=Halo,%20saya%20tertarik%20dengan%20produk%20di%20{current_user.nama_toko}"
        else:
            target_url = f"{settings.FRONTEND_URL}/chat/{current_user.slug}"
    target_url = _validate_redirect_target(target_url)

    link = GrowthLink(
        seller_id=current_user.id,
        code=code,
        source=req.source,
        campaign_name=req.campaign_name,
        target_url=target_url,
    )
    db.add(link)
    await db.commit()

    return {
        "id": link.id,
        "code": code,
        "source": req.source,
        "target_url": target_url,
        "link": f"{settings.BASE_URL}/api/growth-links/{code}/redirect",
        "campaign_name": req.campaign_name,
    }


@router.get("/")
async def list_growth_links(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all growth links for the current seller."""
    result = await db.execute(
        select(GrowthLink)
        .where(GrowthLink.seller_id == current_user.id)
        .order_by(GrowthLink.created_at.desc())
        .limit(100)
    )
    links = result.scalars().all()

    return [
        {
            "id": l.id, "code": l.code, "source": l.source,
            "campaign_name": l.campaign_name, "target_url": l.target_url,
            "click_count": l.click_count, "order_count": l.order_count,
            "revenue": l.revenue, "is_active": l.is_active,
            "link": f"{settings.BASE_URL}/api/growth-links/{l.code}/redirect",
            "created_at": l.created_at.isoformat() if l.created_at else "",
        }
        for l in links
    ]


@router.get("/{code}/redirect")
async def redirect_growth_link(
    code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public redirect endpoint — track click and redirect to target."""
    result = await db.execute(
        select(GrowthLink).where(GrowthLink.code == code, GrowthLink.is_active == True)
    )
    link = result.scalar_one_or_none()

    if not link:
        raise HTTPException(status_code=404, detail="Link tidak ditemukan")

    # Track click
    link.click_count = (link.click_count or 0) + 1
    await db.commit()

    return RedirectResponse(url=link.target_url, status_code=302)


@router.get("/stats")
async def growth_link_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated stats for all growth links."""
    result = await db.execute(
        select(
            func.count(GrowthLink.id),
            func.coalesce(func.sum(GrowthLink.click_count), 0),
            func.coalesce(func.sum(GrowthLink.order_count), 0),
            func.coalesce(func.sum(GrowthLink.revenue), 0),
        ).where(GrowthLink.seller_id == current_user.id)
    )
    row = result.one()

    return {
        "total_links": row[0] or 0,
        "total_clicks": row[1] or 0,
        "total_orders": row[2] or 0,
        "total_revenue": float(row[3] or 0),
    }

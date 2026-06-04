"""
AI Storefront builder endpoints.
Public storefront is read-only, SEO-friendly, no login required.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from config import get_settings
from models.database import get_db
from models.user import User
from models.storefront import Storefront, StorefrontSection
from models.product import Product
from api.routes_auth import get_current_user

router = APIRouter()
settings = get_settings()


class StorefrontUpdateRequest(BaseModel):
    title: Optional[str] = None
    tagline: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    is_published: Optional[bool] = None
    theme_json: Optional[dict] = None


class SectionUpdateRequest(BaseModel):
    type: Optional[str] = None
    title: Optional[str] = None
    content_json: Optional[dict] = None
    order_index: Optional[int] = None
    is_visible: Optional[bool] = None


# ── Public endpoint ──

@router.get("/public/{slug}")
async def get_public_storefront(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """Public storefront page — no login required, SEO-friendly."""
    # Find seller by slug
    seller_result = await db.execute(select(User).where(User.slug == slug))
    seller = seller_result.scalar_one_or_none()
    if not seller:
        raise HTTPException(status_code=404, detail="Toko tidak ditemukan")

    # Get storefront
    sf_result = await db.execute(
        select(Storefront).where(Storefront.seller_id == seller.id)
    )
    sf = sf_result.scalar_one_or_none()

    if not sf or not sf.is_published:
        raise HTTPException(status_code=404, detail="Storefront belum dipublish")

    # Get sections
    sections_result = await db.execute(
        select(StorefrontSection)
        .where(StorefrontSection.storefront_id == sf.id, StorefrontSection.is_visible == True)
        .order_by(StorefrontSection.order_index.asc())
    )
    sections = sections_result.scalars().all()

    # Get featured products
    products_result = await db.execute(
        select(Product)
        .where(Product.seller_id == seller.id, Product.is_active == 1)
        .order_by(Product.created_at.desc())
        .limit(12)
    )
    products = products_result.scalars().all()

    return {
        "store": {
            "name": seller.nama_toko,
            "slug": seller.slug,
            "description": seller.deskripsi_toko,
            "phone": seller.no_hp,
        },
        "storefront": {
            "title": sf.title or seller.nama_toko,
            "tagline": sf.tagline,
            "seo_title": sf.seo_title or seller.nama_toko,
            "seo_description": sf.seo_description or seller.deskripsi_toko,
            "theme": sf.theme_json,
        },
        "sections": [
            {
                "id": s.id,
                "type": s.type,
                "title": s.title,
                "content": s.content_json,
                "order": s.order_index,
            }
            for s in sections
        ],
        "products": [
            {
                "id": p.id,
                "name": p.nama,
                "price": p.harga,
                "description": p.deskripsi,
                "image_url": p.foto_url,
                "category": p.kategori,
            }
            for p in products
        ],
    }


# ── Seller endpoints ──

@router.get("/")
async def get_my_storefront(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Storefront).where(Storefront.seller_id == current_user.id)
    )
    sf = result.scalar_one_or_none()

    if not sf:
        return {"storefront": None, "sections": [], "message": "Belum punya storefront. Generate sekarang!"}

    sections_result = await db.execute(
        select(StorefrontSection)
        .where(StorefrontSection.storefront_id == sf.id)
        .order_by(StorefrontSection.order_index.asc())
    )
    sections = sections_result.scalars().all()

    return {
        "storefront": {
            "id": sf.id,
            "title": sf.title,
            "tagline": sf.tagline,
            "slug": sf.slug,
            "is_published": sf.is_published,
            "seo_title": sf.seo_title,
            "seo_description": sf.seo_description,
            "theme": sf.theme_json,
        },
        "sections": [
            {
                "id": s.id,
                "type": s.type,
                "title": s.title,
                "content": s.content_json,
                "order": s.order_index,
                "is_visible": s.is_visible,
            }
            for s in sections
        ],
    }


@router.patch("/")
async def update_storefront(
    req: StorefrontUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Storefront).where(Storefront.seller_id == current_user.id)
    )
    sf = result.scalar_one_or_none()
    if not sf:
        raise HTTPException(status_code=404, detail="Storefront belum dibuat. Gunakan POST /generate terlebih dahulu.")

    if req.title is not None:
        sf.title = req.title
    if req.tagline is not None:
        sf.tagline = req.tagline
    if req.seo_title is not None:
        sf.seo_title = req.seo_title
    if req.seo_description is not None:
        sf.seo_description = req.seo_description
    if req.is_published is not None:
        sf.is_published = req.is_published
    if req.theme_json is not None:
        sf.theme_json = req.theme_json

    await db.commit()
    return {"message": "Storefront updated"}


@router.post("/generate")
async def generate_storefront(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a draft storefront with default sections from seller data."""
    # Check if already exists
    existing = await db.execute(
        select(Storefront).where(Storefront.seller_id == current_user.id)
    )
    sf = existing.scalar_one_or_none()

    if not sf:
        sf = Storefront(
            seller_id=current_user.id,
            slug=current_user.slug,
            title=current_user.nama_toko,
            tagline=current_user.deskripsi_toko or f"Selamat datang di {current_user.nama_toko}!",
            seo_title=current_user.nama_toko,
            seo_description=current_user.deskripsi_toko or "",
            is_published=False,
        )
        db.add(sf)
        await db.flush()

    # Generate default sections
    default_sections = [
        {
            "type": "hero",
            "title": current_user.nama_toko,
            "content_json": {
                "headline": f"Selamat datang di {current_user.nama_toko}",
                "subheadline": current_user.deskripsi_toko or "Temukan produk terbaik untuk kamu!",
                "cta_text": "Chat Sekarang",
                "cta_url": f"/chat/{current_user.slug}",
            },
            "order_index": 0,
        },
        {
            "type": "featured_products",
            "title": "Produk Unggulan",
            "content_json": {"limit": 6, "sort": "newest"},
            "order_index": 1,
        },
        {
            "type": "categories",
            "title": "Kategori Produk",
            "content_json": {},
            "order_index": 2,
        },
        {
            "type": "testimonials",
            "title": "Apa Kata Pelanggan",
            "content_json": {"items": []},
            "order_index": 3,
        },
        {
            "type": "cta",
            "title": "Hubungi Kami",
            "content_json": {
                "text": f"Mau tanya-tanya? Chat langsung dengan AI kami!",
                "cta_text": "Mulai Chat",
                "cta_url": f"/chat/{current_user.slug}",
                "phone": current_user.no_hp or "",
            },
            "order_index": 4,
        },
    ]

    # Remove existing sections and recreate
    existing_sections = await db.execute(
        select(StorefrontSection).where(StorefrontSection.storefront_id == sf.id)
    )
    for s in existing_sections.scalars().all():
        await db.delete(s)

    for sec_data in default_sections:
        section = StorefrontSection(
            storefront_id=sf.id,
            type=sec_data["type"],
            title=sec_data["title"],
            content_json=sec_data["content_json"],
            order_index=sec_data["order_index"],
        )
        db.add(section)

    await db.commit()
    return {
        "message": "Storefront draft berhasil dibuat! Edit dan publish ketika siap.",
        "storefront_id": sf.id,
        "slug": sf.slug,
    }


@router.patch("/sections/{section_id}")
async def update_section(
    section_id: int,
    req: SectionUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StorefrontSection)
        .join(Storefront, StorefrontSection.storefront_id == Storefront.id)
        .where(StorefrontSection.id == section_id, Storefront.seller_id == current_user.id)
    )
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section tidak ditemukan")

    if req.type is not None:
        section.type = req.type
    if req.title is not None:
        section.title = req.title
    if req.content_json is not None:
        section.content_json = req.content_json
    if req.order_index is not None:
        section.order_index = req.order_index
    if req.is_visible is not None:
        section.is_visible = req.is_visible

    await db.commit()
    return {"message": "Section updated"}

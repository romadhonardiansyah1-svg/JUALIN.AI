"""
JUALIN.AI — Products API Routes
CRUD with auto-embedding + image upload for semantic search
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
from typing import Optional
import os
import uuid as uuid_module

from config import get_settings
from models.database import get_db
from models.user import User
from models.product import Product
from api.routes_auth import get_current_user
from cache import cache_get, cache_set, cache_invalidate_products
from ai.embeddings import generate_embedding, build_embed_text

router = APIRouter()
settings = get_settings()


# ── Pydantic Schemas ──

class ProductCreate(BaseModel):
    nama: str = Field(min_length=1, max_length=255)
    deskripsi: str = ""
    harga: float = Field(ge=0)
    stok: int = Field(default=0, ge=0)
    kategori: str = "umum"
    foto_url: str = ""


class ProductUpdate(BaseModel):
    nama: Optional[str] = Field(default=None, min_length=1, max_length=255)
    deskripsi: Optional[str] = None
    harga: Optional[float] = Field(default=None, ge=0)
    stok: Optional[int] = Field(default=None, ge=0)
    kategori: Optional[str] = None
    foto_url: Optional[str] = None


class ProductResponse(BaseModel):
    id: int
    seller_id: int
    nama: str
    deskripsi: str
    harga: float
    stok: int
    kategori: str
    foto_url: str
    summary: str
    is_active: int

    class Config:
        from_attributes = True


# ── Endpoints ──

@router.get("/", response_model=list[ProductResponse])
async def list_products(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List semua produk seller (cached 5 min, multi-tenant isolated)."""
    cache_key = f"products:{current_user.id}:list"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    result = await db.execute(
        select(Product)
        .where(Product.seller_id == current_user.id)
        .where(Product.is_active == 1)
        .order_by(Product.created_at.desc())
    )
    products = result.scalars().all()
    data = [ProductResponse.model_validate(p).model_dump() for p in products]
    await cache_set(cache_key, data, ttl=300)
    return data


@router.post("/", response_model=ProductResponse, status_code=201)
async def create_product(
    req: ProductCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Tambah produk baru + auto-generate embedding untuk semantic search."""
    # Check product limit per tier
    tier_limits = {
        "free": settings.PRODUCT_LIMIT_FREE,
        "starter": settings.PRODUCT_LIMIT_STARTER,
        "pro": settings.PRODUCT_LIMIT_PRO,
        "bisnis": settings.PRODUCT_LIMIT_BISNIS,
    }
    limit = tier_limits.get(current_user.tier.value, 10)
    
    result = await db.execute(
        select(func.count(Product.id))
        .where(Product.seller_id == current_user.id)
        .where(Product.is_active == 1)
    )
    count = result.scalar()
    
    if count >= limit:
        raise HTTPException(
            status_code=403,
            detail=f"Batas produk tier {current_user.tier.value} ({limit} produk) sudah tercapai. Upgrade untuk menambah lebih banyak produk."
        )
    
    # Generate embedding
    embed_text = build_embed_text(req.model_dump())
    embedding = generate_embedding(embed_text)
    
    # Generate AI summary
    summary = f"{req.nama} - {req.deskripsi}. Harga Rp {req.harga:,.0f}. Kategori: {req.kategori}."
    
    product = Product(
        seller_id=current_user.id,
        nama=req.nama,
        deskripsi=req.deskripsi,
        harga=req.harga,
        stok=req.stok,
        kategori=req.kategori,
        foto_url=req.foto_url,
        summary=summary,
        embedding=embedding,
    )
    
    db.add(product)
    await db.commit()
    await db.refresh(product)
    await cache_invalidate_products(current_user.id)
    
    # Invalidate AI catalog cache so AI uses fresh data (BUG 5 FIX)
    try:
        from ai.agent import invalidate_catalog_cache
        invalidate_catalog_cache(current_user.id)
    except Exception:
        pass
    
    return ProductResponse.model_validate(product)


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    req: ProductUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update produk + re-generate embedding jika deskripsi/nama berubah."""
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .where(Product.seller_id == current_user.id)
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    
    # Update fields
    update_data = req.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)
    
    # Re-generate embedding if text fields changed
    if any(f in update_data for f in ["nama", "deskripsi", "kategori"]):
        embed_text = build_embed_text({
            "nama": product.nama,
            "deskripsi": product.deskripsi,
            "kategori": product.kategori,
            "harga": product.harga,
        })
        product.embedding = generate_embedding(embed_text)
        product.summary = f"{product.nama} - {product.deskripsi}. Harga Rp {product.harga:,.0f}. Kategori: {product.kategori}."
    
    await db.commit()
    await db.refresh(product)
    await cache_invalidate_products(current_user.id)
    
    # Invalidate AI catalog cache (BUG 5 FIX)
    try:
        from ai.agent import invalidate_catalog_cache
        invalidate_catalog_cache(current_user.id)
    except Exception:
        pass
    
    return ProductResponse.model_validate(product)


@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete produk (set is_active = 0)."""
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .where(Product.seller_id == current_user.id)
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    
    product.is_active = 0
    await db.commit()
    await cache_invalidate_products(current_user.id)
    
    # Invalidate AI catalog cache (BUG 5 FIX)
    try:
        from ai.agent import invalidate_catalog_cache
        invalidate_catalog_cache(current_user.id)
    except Exception:
        pass
    
    return {"message": "Produk berhasil dihapus", "id": product_id}


@router.get("/search")
async def search_products(
    q: str,
    seller_id: int,
    limit: int = 5,
    db: AsyncSession = Depends(get_db),
):
    """Semantic search: cari produk berdasarkan deskripsi natural language."""
    query_embedding = generate_embedding(q)
    
    # Use pgvector cosine distance for semantic search
    result = await db.execute(
        select(Product)
        .where(Product.seller_id == seller_id)
        .where(Product.is_active == 1)
        .where(Product.stok > 0)  # Hanya produk yang masih ada stok
        .order_by(Product.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    products = result.scalars().all()
    
    return [
        {
            "id": p.id,
            "nama": p.nama,
            "deskripsi": p.deskripsi,
            "harga": p.harga,
            "stok": p.stok,
            "kategori": p.kategori,
            "foto_url": p.foto_url,
            "summary": p.summary,
        }
        for p in products
    ]


@router.post("/{product_id}/upload-image")
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload foto produk. Supports jpg, png, webp."""
    # Validate product belongs to user
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .where(Product.seller_id == current_user.id)
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Tipe file tidak didukung. Gunakan: JPG, PNG, atau WebP"
        )
    
    # Validate file size (max 5MB)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Ukuran file maksimal 5MB")
    
    # Save file
    uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "products")
    os.makedirs(uploads_dir, exist_ok=True)
    
    ext_map = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }
    ext = ext_map[file.content_type]
    filename = f"{current_user.id}_{product_id}_{uuid_module.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(uploads_dir, filename)
    
    with open(filepath, "wb") as f:
        f.write(contents)
    
    # Update product foto_url
    product.foto_url = f"/uploads/products/{filename}"
    await db.commit()
    await db.refresh(product)
    await cache_invalidate_products(current_user.id)
    
    return {
        "message": "Foto berhasil diupload",
        "foto_url": product.foto_url,
        "product_id": product.id,
    }


@router.post("/{product_id}/ai-enrich")
async def ai_enrich_product(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    AI enrichment preview for a product.
    Returns suggestions but does NOT auto-apply. Seller must approve.
    """
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .where(Product.seller_id == current_user.id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")

    # Calculate catalog health score
    score = 0
    reasons = []
    if product.nama and len(product.nama) > 3:
        score += 20
    else:
        reasons.append("Nama produk terlalu pendek")
    if product.deskripsi and len(product.deskripsi) > 20:
        score += 25
    else:
        reasons.append("Deskripsi kurang detail")
    if product.foto_url:
        score += 20
    else:
        reasons.append("Belum ada foto produk")
    if product.harga and product.harga > 0:
        score += 15
    else:
        reasons.append("Harga belum diset")
    if product.stok and product.stok > 0:
        score += 10
    else:
        reasons.append("Stok habis")
    if product.kategori and product.kategori != "umum":
        score += 10
    else:
        reasons.append("Kategori masih default")

    # Generate SEO suggestions
    seo_title = f"{product.nama} - Beli Online | {current_user.nama_toko}"
    seo_description = product.deskripsi[:160] if product.deskripsi else f"Beli {product.nama} dari {current_user.nama_toko} dengan harga terbaik."

    # Auto-detect tags from description
    tags = []
    if product.deskripsi:
        keywords = ["murah", "premium", "original", "baru", "promo", "diskon", "terlaris", "best seller", "handmade", "import"]
        desc_lower = product.deskripsi.lower()
        tags = [k for k in keywords if k in desc_lower]

    return {
        "product_id": product.id,
        "product_name": product.nama,
        "catalog_score": score,
        "score_reasons": reasons,
        "suggestions": {
            "seo_title": seo_title,
            "seo_description": seo_description,
            "tags": tags,
            "category_suggestion": product.kategori,
        },
        "message": "Preview enrichment. Gunakan PATCH /products/{id} untuk apply.",
    }


@router.get("/insights")
async def product_insights(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Product health overview: scores, categories, alerts."""
    result = await db.execute(
        select(Product)
        .where(Product.seller_id == current_user.id, Product.is_active == 1)
    )
    products = result.scalars().all()

    if not products:
        return {"total": 0, "avg_score": 0, "categories": {}, "alerts": []}

    scores = []
    categories = {}
    alerts = []

    for p in products:
        # Quick score
        s = 0
        if p.nama and len(p.nama) > 3: s += 20
        if p.deskripsi and len(p.deskripsi) > 20: s += 25
        if p.foto_url: s += 20
        if p.harga and p.harga > 0: s += 15
        if p.stok and p.stok > 0: s += 10
        if p.kategori and p.kategori != "umum": s += 10
        scores.append(s)

        cat = p.kategori or "umum"
        categories[cat] = categories.get(cat, 0) + 1

        if (p.stok or 0) == 0:
            alerts.append({"type": "out_of_stock", "product": p.nama, "id": p.id})
        elif (p.stok or 0) <= 5:
            alerts.append({"type": "low_stock", "product": p.nama, "stock": p.stok, "id": p.id})
        if not p.foto_url:
            alerts.append({"type": "no_image", "product": p.nama, "id": p.id})

    return {
        "total": len(products),
        "avg_score": round(sum(scores) / len(scores)) if scores else 0,
        "categories": categories,
        "alerts": alerts[:20],
    }

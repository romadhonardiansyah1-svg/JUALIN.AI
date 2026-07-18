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
import io

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

def _has_valid_image_signature(content_type: str | None, contents: bytes) -> bool:
    if content_type in ("image/jpeg", "image/jpg"):
        return contents.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return contents.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(contents) >= 12 and contents[:4] == b"RIFF" and contents[8:12] == b"WEBP"
    return False


def _sanitize_image_upload(content_type: str | None, contents: bytes) -> bytes:
    from PIL import Image, ImageOps, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = 20_000_000
    target_format = {
        "image/jpeg": "JPEG",
        "image/jpg": "JPEG",
        "image/png": "PNG",
        "image/webp": "WEBP",
    }.get(content_type)
    if not target_format:
        raise HTTPException(status_code=400, detail="Tipe file tidak didukung")

    try:
        with Image.open(io.BytesIO(contents)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(contents)) as image:
            image = ImageOps.exif_transpose(image)
            if image.width <= 0 or image.height <= 0 or image.width * image.height > Image.MAX_IMAGE_PIXELS:
                raise HTTPException(status_code=400, detail="Dimensi gambar tidak valid")

            output = io.BytesIO()
            if target_format == "JPEG":
                if image.mode in ("RGBA", "LA", "P"):
                    background = Image.new("RGB", image.size, (255, 255, 255))
                    if image.mode == "P":
                        image = image.convert("RGBA")
                    background.paste(image, mask=image.getchannel("A") if "A" in image.getbands() else None)
                    image = background
                else:
                    image = image.convert("RGB")
                image.save(output, format="JPEG", quality=85, optimize=True)
            elif target_format == "PNG":
                image.save(output, format="PNG", optimize=True)
            else:
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGB")
                image.save(output, format="WEBP", quality=85, method=6)
            return output.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(status_code=400, detail="File gambar tidak valid atau rusak")


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
    is_active: Optional[int] = Field(default=None, ge=0, le=1)


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
    """List all seller products, including onboarding drafts."""
    cache_key = f"products:{current_user.id}:list"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    result = await db.execute(
        select(Product)
        .where(Product.seller_id == current_user.id)
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
    from core.quota import lock_product_quota
    await lock_product_quota(db, current_user.id)

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
    """Update a seller product while enforcing active-product tier limits."""
    update_data = req.model_dump(exclude_unset=True)
    if update_data.get("is_active") == 1:
        from core.quota import lock_product_quota
        await lock_product_quota(db, current_user.id)

    result = await db.execute(
        select(Product)
        .where(Product.id == product_id)
        .where(Product.seller_id == current_user.id)
        .with_for_update()
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")

    if update_data.get("is_active") == 1 and product.is_active != 1:
        tier_limits = {
            "free": settings.PRODUCT_LIMIT_FREE,
            "starter": settings.PRODUCT_LIMIT_STARTER,
            "pro": settings.PRODUCT_LIMIT_PRO,
            "bisnis": settings.PRODUCT_LIMIT_BISNIS,
        }
        limit = tier_limits.get(current_user.tier.value, 10)
        count_result = await db.execute(
            select(func.count(Product.id))
            .where(Product.seller_id == current_user.id)
            .where(Product.is_active == 1)
        )
        active_count = count_result.scalar() or 0
        if active_count >= limit:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Batas produk tier {current_user.tier.value} ({limit} produk) "
                    "sudah tercapai. Upgrade untuk mengaktifkan produk ini."
                ),
            )

    for field, value in update_data.items():
        setattr(product, field, value)

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
    if not contents or not _has_valid_image_signature(file.content_type, contents):
        raise HTTPException(status_code=400, detail="File gambar tidak valid atau rusak")
    
    contents = _sanitize_image_upload(file.content_type, contents)

    # Save re-encoded file under a seller-specific path.
    uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "products")
    seller_uploads_dir = os.path.join(uploads_dir, str(current_user.id))
    os.makedirs(seller_uploads_dir, exist_ok=True)
    
    ext_map = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }
    ext = ext_map[file.content_type]
    filename = f"{product_id}_{uuid_module.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(seller_uploads_dir, filename)
    
    with open(filepath, "wb") as f:
        f.write(contents)

    old_foto_url = product.foto_url or ""
    if old_foto_url.startswith("/uploads/products/"):
        old_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            old_foto_url.lstrip("/").replace("/", os.sep),
        )
        old_path = os.path.abspath(old_path)
        uploads_root = os.path.abspath(uploads_dir)
        if old_path.startswith(uploads_root) and old_path != os.path.abspath(filepath) and os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
    
    # Update product foto_url
    product.foto_url = f"/uploads/products/{current_user.id}/{filename}"
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

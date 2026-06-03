"""
JUALIN.AI — Products API Routes
CRUD with auto-embedding for semantic search
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional

from config import get_settings
from models.database import get_db
from models.user import User
from models.product import Product
from api.routes_auth import get_current_user
from cache import cache_get, cache_set, cache_invalidate_products

router = APIRouter()
settings = get_settings()

# Lazy-loaded embedding model
_embed_model = None


def get_embedding_model():
    """Lazy-load embedding model (only loaded once on first use)."""
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer(settings.EMBEDDING_MODEL)
        print(f"✅ Embedding model loaded: {settings.EMBEDDING_MODEL}")
    return _embed_model


def generate_embedding(text: str) -> list[float]:
    """Generate embedding vector from text."""
    model = get_embedding_model()
    return model.encode(text).tolist()


def build_embed_text(product: dict) -> str:
    """Build text for embedding from product data."""
    parts = [
        product.get("nama", ""),
        product.get("deskripsi", ""),
        product.get("kategori", ""),
        f"harga {product.get('harga', 0)}",
    ]
    return " ".join(p for p in parts if p)


# ── Pydantic Schemas ──

class ProductCreate(BaseModel):
    nama: str
    deskripsi: str = ""
    harga: float
    stok: int = 0
    kategori: str = "umum"
    foto_url: str = ""


class ProductUpdate(BaseModel):
    nama: Optional[str] = None
    deskripsi: Optional[str] = None
    harga: Optional[float] = None
    stok: Optional[int] = None
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

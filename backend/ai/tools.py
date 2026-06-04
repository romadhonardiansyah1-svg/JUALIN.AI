"""
JUALIN.AI — Agent Tools
Tools yang digunakan AI agent untuk akses database
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import secrets

from config import get_settings
from models.product import Product
from models.order import Order, OrderStatus
from ai.embeddings import generate_embedding

settings = get_settings()


async def tool_cek_produk(product_id: int, db: AsyncSession) -> dict:
    """Cek detail produk berdasarkan ID."""
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.is_active == 1)
    )
    p = result.scalar_one_or_none()
    if not p:
        return {"error": "Produk tidak ditemukan"}
    return {
        "id": p.id, "nama": p.nama, "deskripsi": p.deskripsi,
        "harga": p.harga, "stok": p.stok, "kategori": p.kategori,
        "foto_url": p.foto_url,
    }


async def tool_cari_produk(query: str, seller_id: int, db: AsyncSession, limit: int = 5) -> list[dict]:
    """Semantic search produk berdasarkan deskripsi natural language."""
    query_embedding = generate_embedding(query)
    
    result = await db.execute(
        select(Product)
        .where(Product.seller_id == seller_id)
        .where(Product.is_active == 1)
        .where(Product.stok > 0)
        .order_by(Product.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    products = result.scalars().all()
    
    return [
        {
            "id": p.id, "nama": p.nama, "deskripsi": p.deskripsi,
            "harga": p.harga, "stok": p.stok, "kategori": p.kategori,
        }
        for p in products
    ]


async def tool_hitung_total(items: list[dict]) -> dict:
    """
    Hitung total harga dari daftar item.
    items: [{"nama": "Baju Pink", "harga": 89000, "qty": 2}]
    """
    total = sum(item.get("harga", 0) * item.get("qty", 1) for item in items)
    summary = "\n".join(
        f"  {i+1}. {item['nama']} × {item.get('qty', 1)} = Rp {item['harga'] * item.get('qty', 1):,.0f}"
        for i, item in enumerate(items)
    )
    return {
        "items_count": len(items),
        "total": total,
        "summary": summary,
        "formatted": f"Rp {total:,.0f}",
    }


async def tool_buat_order(
    seller_id: int,
    customer_name: str,
    customer_phone: str,
    customer_address: str,
    items: list[dict],
    conversation_id: int,
    db: AsyncSession,
) -> dict:
    """
    Buat order baru dari percakapan.
    Auto-kurangi stok produk.
    """
    total = sum(item.get("harga", 0) * item.get("qty", 1) for item in items)
    
    # Kurangi stok
    for item in items:
        if "product_id" in item:
            result = await db.execute(
                select(Product).where(Product.id == item["product_id"])
            )
            product = result.scalar_one_or_none()
            if product:
                qty = item.get("qty", 1)
                if product.stok < qty:
                    return {"error": f"Stok {product.nama} tidak cukup (sisa {product.stok})"}
                product.stok -= qty
    
    # Buat order
    order = Order(
        seller_id=seller_id,
        conversation_id=conversation_id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_address=customer_address,
        items=items,
        total=total,
        status=OrderStatus.PENDING,
        payment_access_token=secrets.token_urlsafe(32),
    )
    
    db.add(order)
    await db.commit()
    await db.refresh(order)
    
    return {
        "order_id": order.id,
        "total": total,
        "formatted": f"Rp {total:,.0f}",
        "status": "pending",
        "payment_url": f"{settings.FRONTEND_URL.rstrip('/')}/pay/{order.id}?token={order.payment_access_token}",
        "message": f"Order #{order.id} berhasil dibuat! Total: Rp {total:,.0f}",
    }


async def tool_cek_status_order(order_id: int, db: AsyncSession) -> dict:
    """Cek status order berdasarkan ID."""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        return {"error": "Order tidak ditemukan"}
    
    status_text = {
        "pending": "Menunggu pembayaran",
        "paid": "Sudah dibayar, sedang diproses",
        "shipped": "Sudah dikirim",
        "done": "Selesai",
        "cancelled": "Dibatalkan",
    }
    
    return {
        "order_id": order.id,
        "status": order.status.value if hasattr(order.status, 'value') else order.status,
        "status_text": status_text.get(str(order.status.value if hasattr(order.status, 'value') else order.status), "Unknown"),
        "total": order.total,
        "created_at": str(order.created_at),
    }

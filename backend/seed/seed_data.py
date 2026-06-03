"""
JUALIN.AI — Seed Data
15 produk toko baju demo untuk testing dan demo lomba
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from models.database import engine, async_session, init_db
from models.user import User, UserTier, UserRole
from models.product import Product
from api.routes_auth import hash_password, create_slug


DEMO_PRODUCTS = [
    {"nama": "Baju Pink Satin", "deskripsi": "Baju satin warna pink soft, cocok untuk pesta dan kondangan. Bahan halus dan nyaman dipakai.", "harga": 89000, "stok": 15, "kategori": "dress"},
    {"nama": "Dress Emerald Elegan", "deskripsi": "Dress panjang warna hijau emerald, bahan premium dengan detail payet. Cocok untuk acara formal.", "harga": 189000, "stok": 8, "kategori": "dress"},
    {"nama": "Kaos Oversize Hitam", "deskripsi": "Kaos oversize warna hitam polos, bahan cotton combed 30s. Nyaman untuk daily wear.", "harga": 59000, "stok": 30, "kategori": "kaos"},
    {"nama": "Kaos Oversize Putih", "deskripsi": "Kaos oversize warna putih polos, bahan cotton combed 30s. Cocok untuk outfit casual.", "harga": 59000, "stok": 25, "kategori": "kaos"},
    {"nama": "Blouse Brukat Gold", "deskripsi": "Blouse brukat warna gold, detail bordir bunga. Cocok untuk wisuda dan kondangan.", "harga": 145000, "stok": 10, "kategori": "blouse"},
    {"nama": "Gamis Pesta Navy", "deskripsi": "Gamis pesta warna navy blue, bahan wolfis premium dengan belt. Anggun dan syari.", "harga": 225000, "stok": 6, "kategori": "gamis"},
    {"nama": "Celana Cargo Hijau", "deskripsi": "Celana cargo warna hijau army, banyak kantong, bahan tebal. Cocok untuk outdoor dan hiking.", "harga": 135000, "stok": 12, "kategori": "celana"},
    {"nama": "Hoodie Abu-abu", "deskripsi": "Hoodie fleece warna abu-abu, hangat dan tebal. Ada kantong depan dan tali hoodie.", "harga": 125000, "stok": 18, "kategori": "hoodie"},
    {"nama": "Kemeja Flanel Merah", "deskripsi": "Kemeja flanel kotak-kotak merah hitam, bahan katun tebal. Style casual masculine.", "harga": 95000, "stok": 14, "kategori": "kemeja"},
    {"nama": "Rok Plisket Cream", "deskripsi": "Rok plisket panjang warna cream, bahan premium tidak mudah kusut. Elegan dan versatile.", "harga": 79000, "stok": 20, "kategori": "rok"},
    {"nama": "Jaket Jeans Biru", "deskripsi": "Jaket jeans denim biru classic, potongan regular fit. Timeless fashion item.", "harga": 175000, "stok": 7, "kategori": "jaket"},
    {"nama": "Cardigan Rajut Pastel", "deskripsi": "Cardigan rajut warna pastel lilac, lembut dan ringan. Cocok untuk layering.", "harga": 89000, "stok": 16, "kategori": "cardigan"},
    {"nama": "Celana Jeans Skinny", "deskripsi": "Celana jeans skinny fit warna biru gelap, bahan stretch nyaman. Cocok untuk casual dan semi-formal.", "harga": 149000, "stok": 22, "kategori": "celana"},
    {"nama": "T-shirt Band Vintage", "deskripsi": "T-shirt band vintage rock, sablon premium warna-warni. Edisi terbatas.", "harga": 75000, "stok": 0, "kategori": "kaos"},
    {"nama": "Dress Casual Bunga", "deskripsi": "Dress casual motif bunga-bunga, bahan katun rayon adem. Cocok untuk jalan-jalan dan hangout.", "harga": 99000, "stok": 11, "kategori": "dress"},
]


async def seed():
    """Seed database with demo data."""
    await init_db()
    
    async with async_session() as db:
        # Check if demo user exists
        result = await db.execute(select(User).where(User.email == "demo@jualin.ai"))
        existing = result.scalar_one_or_none()
        
        if existing:
            print("⚠️ Demo data already exists. Skipping seed.")
            return
        
        # Create demo seller
        demo_seller = User(
            email="demo@jualin.ai",
            password_hash=hash_password("demo123"),
            nama_toko="Toko Sari Fashion",
            slug="toko-sari-fashion",
            deskripsi_toko="Toko baju online terlengkap! Baju pesta, casual, gamis, dan lainnya.",
            no_hp="0812-3456-7890",
            tier=UserTier.PRO,
            role=UserRole.SELLER,
            ai_active=True,
            ai_style="santai",
        )
        db.add(demo_seller)
        await db.commit()
        await db.refresh(demo_seller)
        
        print(f"✅ Demo seller created: {demo_seller.nama_toko} (slug: {demo_seller.slug})")
        
        # Create admin user
        admin_user = User(
            email="admin@jualin.ai",
            password_hash=hash_password("admin123"),
            nama_toko="JUALIN.AI Admin",
            slug="admin",
            tier=UserTier.BISNIS,
            role=UserRole.ADMIN,
        )
        db.add(admin_user)
        await db.commit()
        
        print("✅ Admin user created: admin@jualin.ai")
        
        # Create products with embeddings
        print("📦 Seeding products...")
        
        try:
            from api.routes_products import generate_embedding, build_embed_text
            use_embeddings = True
            print("✅ Embedding model loaded")
        except Exception as e:
            print(f"⚠️ Embedding model not available ({e}), seeding without vectors")
            use_embeddings = False
        
        for p_data in DEMO_PRODUCTS:
            embedding = None
            if use_embeddings:
                embed_text = build_embed_text(p_data)
                embedding = generate_embedding(embed_text)
            
            product = Product(
                seller_id=demo_seller.id,
                nama=p_data["nama"],
                deskripsi=p_data["deskripsi"],
                harga=p_data["harga"],
                stok=p_data["stok"],
                kategori=p_data["kategori"],
                summary=f"{p_data['nama']} - {p_data['deskripsi'][:80]}. Harga Rp {p_data['harga']:,.0f}.",
                embedding=embedding,
            )
            db.add(product)
            print(f"  + {p_data['nama']} (Rp {p_data['harga']:,.0f}, stok: {p_data['stok']})")
        
        await db.commit()
        print(f"\n🎉 Seed complete! {len(DEMO_PRODUCTS)} products added to '{demo_seller.nama_toko}'")
        print(f"\n📝 Login credentials:")
        print(f"   Seller: demo@jualin.ai / demo123")
        print(f"   Admin:  admin@jualin.ai / admin123")
        print(f"   Chat:   /chat/{demo_seller.slug}")


if __name__ == "__main__":
    asyncio.run(seed())

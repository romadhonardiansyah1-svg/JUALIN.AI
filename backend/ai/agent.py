"""
JUALIN.AI — AI Agent
LangGraph-based sales agent with catalog-aware RAG and guardrails
"""
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import get_settings
from models.product import Product
from models.conversation import Message, MessageRole
from models.order import Order
from ai.prompts import get_system_prompt
from ai.guardrails import apply_guardrails

settings = get_settings()

# LLM Client (connects to 9Router or direct API)
llm_client = AsyncOpenAI(
    base_url=settings.LLM_BASE_URL,
    api_key=settings.LLM_API_KEY,
)


async def search_products_semantic(query: str, seller_id: int, db: AsyncSession, limit: int = 5) -> list[dict]:
    """Semantic search for products using pgvector."""
    try:
        from api.routes_products import generate_embedding
        query_embedding = generate_embedding(query)
        
        result = await db.execute(
            select(Product)
            .where(Product.seller_id == seller_id)
            .where(Product.is_active == 1)
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
            }
            for p in products
        ]
    except Exception as e:
        print(f"⚠️ Semantic search failed, falling back to keyword: {e}")
        # Fallback to keyword search
        result = await db.execute(
            select(Product)
            .where(Product.seller_id == seller_id)
            .where(Product.is_active == 1)
            .where(Product.stok > 0)
            .limit(limit)
        )
        return [
            {
                "id": p.id,
                "nama": p.nama,
                "deskripsi": p.deskripsi,
                "harga": p.harga,
                "stok": p.stok,
                "kategori": p.kategori,
            }
            for p in result.scalars().all()
        ]


async def get_all_products(seller_id: int, db: AsyncSession) -> list[dict]:
    """Get all active products for a seller (for catalog context)."""
    result = await db.execute(
        select(Product)
        .where(Product.seller_id == seller_id)
        .where(Product.is_active == 1)
        .order_by(Product.nama)
    )
    products = result.scalars().all()
    
    return [
        {
            "nama": p.nama,
            "harga": f"Rp {p.harga:,.0f}",
            "stok": p.stok,
            "kategori": p.kategori,
            "deskripsi": p.deskripsi[:100] if p.deskripsi else "",
        }
        for p in products
    ]


def format_catalog_context(products: list[dict]) -> str:
    """Format product catalog for AI system prompt."""
    if not products:
        return "Katalog kosong — belum ada produk yang ditambahkan."
    
    lines = ["KATALOG PRODUK TOKO:"]
    for i, p in enumerate(products, 1):
        status = "✅ Ready" if p["stok"] > 0 else "❌ Habis"
        lines.append(
            f"{i}. {p['nama']} — {p['harga']} — Stok: {p['stok']} ({status}) — {p['kategori']}"
        )
        if p.get("deskripsi"):
            lines.append(f"   Deskripsi: {p['deskripsi']}")
    
    return "\n".join(lines)


def format_chat_history(messages: list) -> list[dict]:
    """Format chat history for LLM messages format."""
    formatted = []
    for msg in messages:
        if isinstance(msg, Message):
            role = "user" if msg.role == MessageRole.CUSTOMER else "assistant"
            formatted.append({"role": role, "content": msg.content})
        elif isinstance(msg, dict):
            formatted.append(msg)
    return formatted


async def get_ai_response(
    message: str,
    seller_id: int,
    conversation_history: list,
    seller_style: str,
    db: AsyncSession,
    memory_context: str = "",
) -> str:
    """
    Main AI agent function:
    1. Get catalog from DB (real-time)
    2. Search relevant products (semantic)
    3. Build context with guardrails + customer memory
    4. Call LLM
    5. Apply post-processing guardrails
    """
    
    # 1. Get full catalog (real-time stock)
    all_products = await get_all_products(seller_id, db)
    catalog_text = format_catalog_context(all_products)
    
    # 2. Semantic search for relevant products
    relevant_products = await search_products_semantic(message, seller_id, db, limit=3)
    
    relevant_text = ""
    if relevant_products:
        relevant_text = "\nPRODUK PALING RELEVAN DENGAN PERTANYAAN CUSTOMER:\n"
        for p in relevant_products:
            status = "READY" if p["stok"] > 0 else "HABIS STOK"
            relevant_text += f"- {p['nama']}: Rp {p['harga']:,.0f}, Stok: {p['stok']} ({status})\n"
            if p.get("deskripsi"):
                relevant_text += f"  Detail: {p['deskripsi'][:150]}\n"
    
    # 3. Build system prompt with catalog + guardrails + memory
    system_prompt = get_system_prompt(
        seller_style=seller_style,
        catalog=catalog_text,
        relevant_products=relevant_text,
    )
    
    # Inject customer memory (if returning customer)
    if memory_context:
        system_prompt += "\n" + memory_context
    
    # 4. Build messages for LLM
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(format_chat_history(conversation_history[:-1]))  # Exclude last (it's the current message)
    messages.append({"role": "user", "content": message})
    
    # 5. Call LLM
    try:
        response = await llm_client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=500,
        )
        ai_text = response.choices[0].message.content
    except Exception as e:
        print(f"❌ LLM Error: {e}")
        # Fallback response
        if relevant_products and relevant_products[0]["stok"] > 0:
            p = relevant_products[0]
            ai_text = (
                f"Hai kak! 😊 Kami punya {p['nama']} seharga Rp {p['harga']:,.0f}. "
                f"Stok masih ada {p['stok']} pcs. Mau order kak?"
            )
        else:
            ai_text = "Hai kak! Ada yang bisa kami bantu? Silakan tanya-tanya produk kami ya 😊"
    
    # 6. Apply guardrails (post-processing)
    ai_text = apply_guardrails(ai_text, all_products)
    
    return ai_text

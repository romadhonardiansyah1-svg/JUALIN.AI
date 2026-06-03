"""
JUALIN.AI — AI Agent
LangGraph-based sales agent with catalog-aware RAG and guardrails
Optimized: intent detection, catalog caching, parallel calls
"""
import re
import asyncio
import time
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
    timeout=20.0,  # 20 second timeout (default was 600s = 10 min!)
    max_retries=1,  # 1 retry on failure
)

# ── In-memory catalog cache ──
_catalog_cache = {}  # seller_id -> {"data": [...], "timestamp": float}
CATALOG_CACHE_TTL = 300  # 5 minutes


def _is_cache_valid(seller_id: int) -> bool:
    """Check if cached catalog is still valid."""
    if seller_id not in _catalog_cache:
        return False
    return (time.time() - _catalog_cache[seller_id]["timestamp"]) < CATALOG_CACHE_TTL


# ── Intent Detection ──

# Keywords for non-product queries (kebijakan, pengiriman, dll)
_NON_PRODUCT_KEYWORDS = [
    r'\bcod\b', r'\bcash\s*on\s*delivery\b',
    r'\bongkir\b', r'\bongkos\s*kirim\b', r'\bbiaya\s*kirim\b',
    r'\bretur\b', r'\breturn\b', r'\btukar\b', r'\brefund\b',
    r'\bgaransi\b', r'\bwarranty\b',
    r'\bbayar\b', r'\btransfer\b', r'\bpembayaran\b', r'\bdana\b', r'\bovo\b', r'\bgopay\b',
    r'\bpengiriman\b', r'\bkirim\b', r'\bestimasi\b', r'\bsampai\b',
    r'\bcara\s*order\b', r'\bcara\s*beli\b', r'\bgimana\s*beli\b',
    r'\bminimal\s*order\b', r'\bmin\s*order\b',
    r'\bjam\s*operasional\b', r'\bjam\s*buka\b',
]

_SMALLTALK_KEYWORDS = [
    r'^(halo|hai|hi|hey|hello|pagi|siang|sore|malam|selamat)',
    r'^(makasih|terima\s*kasih|thanks|thank\s*you|ok|oke|okee|sip|siap|mantap)',
    r'^(bye|dadah|sampai\s*jumpa)',
]

_PRODUCT_KEYWORDS = [
    r'\bada\s', r'\bjual\b', r'\bharga\b', r'\bstok\b', r'\bready\b',
    r'\bproduk\b', r'\bbarang\b', r'\bkatalog\b', r'\blist\b',
    r'\bbeli\b', r'\border\b', r'\bpesan\b', r'\bmau\s*(ambil|beli|order)\b',
    r'\brekomendasi\b', r'\bpaling\s*laris\b', r'\btermurah\b', r'\btermahal\b',
    r'\bwarna\b', r'\bukuran\b', r'\bsize\b', r'\bmodel\b',
]


def detect_intent(message: str) -> str:
    """
    Detect user intent from message text.
    Returns: 'product', 'policy', 'smalltalk', 'order', or 'general'
    """
    msg_lower = message.lower().strip()
    
    # Check smalltalk first (greetings, thanks)
    for pattern in _SMALLTALK_KEYWORDS:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            # But if it also contains product keywords, treat as product
            for pk in _PRODUCT_KEYWORDS:
                if re.search(pk, msg_lower, re.IGNORECASE):
                    return "product"
            return "smalltalk"
    
    # Check non-product (policy) queries
    policy_score = 0
    for pattern in _NON_PRODUCT_KEYWORDS:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            policy_score += 1
    
    # Check product queries
    product_score = 0
    for pattern in _PRODUCT_KEYWORDS:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            product_score += 1
    
    # Decide based on scores
    if policy_score > 0 and policy_score >= product_score:
        return "policy"
    if product_score > 0:
        return "product"
    
    # Default: general (let LLM decide)
    return "general"


async def search_products_semantic(query: str, seller_id: int, db: AsyncSession, limit: int = 5) -> list[dict]:
    """Semantic search for products using pgvector."""
    try:
        from ai.embeddings import generate_embedding
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
    """Get all active products for a seller (with in-memory caching)."""
    # Check cache first
    if _is_cache_valid(seller_id):
        return _catalog_cache[seller_id]["data"]
    
    result = await db.execute(
        select(Product)
        .where(Product.seller_id == seller_id)
        .where(Product.is_active == 1)
        .order_by(Product.nama)
    )
    products = result.scalars().all()
    
    data = [
        {
            "nama": p.nama,
            "harga": f"Rp {p.harga:,.0f}",
            "stok": p.stok,
            "kategori": p.kategori,
            "deskripsi": p.deskripsi[:100] if p.deskripsi else "",
        }
        for p in products
    ]
    
    # Update cache
    _catalog_cache[seller_id] = {"data": data, "timestamp": time.time()}
    
    return data


def invalidate_catalog_cache(seller_id: int):
    """Call this when products are updated."""
    _catalog_cache.pop(seller_id, None)


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
    Main AI agent function (optimized):
    1. Detect intent (product vs policy vs smalltalk)
    2. Get catalog from cache (or DB)
    3. Only do semantic search for product queries
    4. Build context with guardrails + customer memory
    5. Call LLM with optimized token count
    6. Apply post-processing guardrails
    """
    
    # 1. Detect intent
    intent = detect_intent(message)
    
    # 2. Get full catalog (cached)
    all_products = await get_all_products(seller_id, db)
    catalog_text = format_catalog_context(all_products)
    
    # 3. Semantic search ONLY for product-related queries
    relevant_text = ""
    if intent == "product":
        try:
            relevant_products = await search_products_semantic(message, seller_id, db, limit=3)
            if relevant_products:
                relevant_text = "\nPRODUK PALING RELEVAN DENGAN PERTANYAAN CUSTOMER:\n"
                for p in relevant_products:
                    status = "READY" if p["stok"] > 0 else "HABIS STOK"
                    relevant_text += f"- {p['nama']}: Rp {p['harga']:,.0f}, Stok: {p['stok']} ({status})\n"
                    if p.get("deskripsi"):
                        relevant_text += f"  Detail: {p['deskripsi'][:150]}\n"
        except Exception as e:
            print(f"⚠️ Semantic search skipped: {e}")
    
    # 4. Build system prompt with catalog + guardrails + memory
    system_prompt = get_system_prompt(
        seller_style=seller_style,
        catalog=catalog_text,
        relevant_products=relevant_text,
    )
    
    # Inject customer memory (if returning customer)
    if memory_context:
        system_prompt += "\n" + memory_context
    
    # Inject intent hint for the AI
    intent_hints = {
        "policy": "\n⚠️ INTENT TERDETEKSI: Customer bertanya tentang KEBIJAKAN TOKO. Jawab dari panduan kebijakan. JANGAN rekomendasi produk.",
        "smalltalk": "\n⚠️ INTENT TERDETEKSI: Customer menyapa/small talk. Balas ramah dan tanya ada yang bisa dibantu.",
        "product": "\n⚠️ INTENT TERDETEKSI: Customer bertanya tentang PRODUK. Jawab berdasarkan katalog.",
    }
    if intent in intent_hints:
        system_prompt += intent_hints[intent]
    
    # 5. Build messages for LLM (reduced history for speed)
    messages = [{"role": "system", "content": system_prompt}]
    history = format_chat_history(conversation_history[:-1])  # Exclude current
    # Only keep last 6 messages for faster response
    messages.extend(history[-6:])
    messages.append({"role": "user", "content": message})
    
    # 6. Call LLM with optimized settings
    try:
        response = await llm_client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=350,  # Reduced from 500 for faster response
        )
        ai_text = response.choices[0].message.content
    except Exception as e:
        print(f"❌ LLM Error: {e}")
        # Smart fallback based on intent
        if intent == "policy":
            ai_text = "Hai kak! 😊 Untuk info kebijakan toko, silakan hubungi kami langsung ya. Ada yang lain yang bisa dibantu?"
        elif intent == "smalltalk":
            ai_text = "Hai kak! 😊 Selamat datang! Ada yang bisa kami bantu? Silakan tanya-tanya produk kami ya!"
        elif intent == "product" and all_products:
            ai_text = (
                f"Hai kak! 😊 Kami punya {len(all_products)} produk yang bisa dicek. "
                f"Mau tanya produk yang mana kak?"
            )
        else:
            ai_text = "Hai kak! Ada yang bisa kami bantu? Silakan tanya-tanya produk kami ya 😊"
    
    # 7. Apply guardrails (post-processing)
    ai_text = apply_guardrails(ai_text, all_products)
    
    return ai_text

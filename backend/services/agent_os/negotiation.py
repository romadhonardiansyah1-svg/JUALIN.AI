"""
JUALIN OS — Mesin Negosiasi (Juru Tawar AI).

PRINSIP UTAMA: ANGKA dikontrol fungsi deterministik (decide_offer), KATA dirangkai LLM.
Harga penawaran DIJAMIN berada di rentang [floor_price, list_price] — tidak pernah jual rugi.
"""
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from core.logging_config import get_logger
from models.product import Product
from models.agent_os import AgentRun, AgentApproval, NegotiationState
from services.agent_os.policy import get_or_create_policy

settings = get_settings()
logger = get_logger(__name__)


# ── Deteksi intent negosiasi ──
_NEGO_PATTERNS = [
    r'\bboleh\s*kurang\b', r'\bbisa\s*kurang\b', r'\bnego\b', r'\bngenego\b',
    r'\bkurangin\b', r'\bmurahin\b', r'\bpotongan\b', r'\bdiskon\b', r'\btawar\b',
    r'\bboleh\s*\d{2,}', r'\bkalau\s*\d{2,}', r'\b\d+\s*(rb|ribu|k)\b', r'\b\d+\s*aja\b',
    r'\bgocengan\b', r'\bsadis\b',
]


def is_negotiation(text: str) -> bool:
    """True jika pesan mengandung sinyal tawar-menawar."""
    t = (text or "").lower()
    return any(re.search(p, t) for p in _NEGO_PATTERNS)


def parse_price_ask(text: str) -> float | None:
    """
    Ekstrak harga yang diminta customer (dalam rupiah). None jika tidak ada.
    Contoh: '150 ribu'/'150rb'/'150k' -> 150000 ; 'rp 150000' -> 150000 ;
            'boleh 75?' -> 75000 (angka 2-3 digit dianggap ribuan).
    """
    t = (text or "").lower().replace(".", "").replace(",", "")
    m = re.search(r'(\d+)\s*(rb|ribu|k)\b', t)
    if m:
        return float(m.group(1)) * 1000
    m = re.search(r'rp\s*(\d{3,9})', t)
    if m:
        return float(m.group(1))
    m = re.search(r'\b(\d{4,9})\b', t)        # angka 4-9 digit = harga utuh
    if m:
        return float(m.group(1))
    m = re.search(r'\b(\d{2,3})\b', t)         # angka 2-3 digit di konteks nego = ribuan
    if m:
        return float(m.group(1)) * 1000
    return None


def compute_floor_price(list_price: float, cost_price: float, policy) -> float:
    """
    Lantai harga = batas terendah yang boleh ditawarkan.
    = max( harga * (1 - diskon_maks%), modal * (1 + margin_floor%) ).
    Jika modal tidak diketahui (0), pakai batas diskon saja.
    """
    by_discount = list_price * (1 - policy.max_discount_percent / 100.0)
    if cost_price and cost_price > 0:
        by_margin = cost_price * (1 + policy.margin_floor_percent / 100.0)
        return max(by_discount, by_margin)
    return by_discount


def decide_offer(list_price: float, floor_price: float, customer_ask: float | None,
                 round_index: int, policy) -> dict:
    """
    Fungsi DETERMINISTIK. Mengembalikan penawaran yang DIJAMIN di [floor_price, list_price].

    Concession ladder: ronde 0 -> beri 40% jalan dari list ke floor, ronde 1 -> 70%, ronde 2+ -> 100% (floor).
    """
    rounds_max = max(1, policy.nego_max_rounds)
    schedule = [0.40, 0.70, 1.00]
    frac = schedule[min(round_index, len(schedule) - 1)]
    concession_price = list_price - (list_price - floor_price) * frac  # >= floor

    if customer_ask is None:
        offer, decision = concession_price, "counter"
    elif customer_ask >= list_price:
        offer, decision = list_price, "accept"
    elif customer_ask >= concession_price:
        # Permintaan customer di atas garis konsesi -> kabulkan (tetap >= floor)
        offer, decision = customer_ask, "accept"
    elif customer_ask >= floor_price:
        # Di bawah konsesi ronde ini tapi masih di atas floor -> tawar di garis konsesi
        offer, decision = concession_price, "counter"
    else:
        # Di bawah floor -> tawar harga terbaik ronde ini (tidak pernah di bawah floor)
        offer, decision = concession_price, "counter_floor"

    offer = round(max(floor_price, min(offer, list_price)))
    discount_pct = 0.0 if list_price <= 0 else round((list_price - offer) / list_price * 100, 1)
    is_final = round_index >= rounds_max - 1 or offer <= floor_price + 0.5
    requires_approval = discount_pct > policy.require_approval_above_percent
    return {
        "decision": decision,
        "offer_price": offer,
        "discount_pct": discount_pct,
        "floor_price": round(floor_price),
        "list_price": round(list_price),
        "is_final": is_final,
        "requires_approval": requires_approval,
        "round": round_index,
    }


async def _resolve_focus_product(seller_id, conversation, history, message, db):
    """Tebak produk yang sedang ditawar dari konteks percakapan (pgvector)."""
    from ai.agent import search_products_semantic
    texts = []
    for m in (history or [])[-4:]:
        c = getattr(m, "content", None)
        if c is None and isinstance(m, dict):
            c = m.get("content", "")
        if c:
            texts.append(c)
    texts.append(message or "")
    query = " ".join(texts).strip()
    if not query:
        return None
    results = await search_products_semantic(query, seller_id, db, limit=1)
    if not results:
        return None
    r = await db.execute(select(Product).where(Product.id == results[0]["id"]))
    return r.scalar_one_or_none()


async def _get_or_create_state(seller_id, conversation_id, product, policy, db) -> NegotiationState:
    r = await db.execute(
        select(NegotiationState)
        .where(NegotiationState.conversation_id == conversation_id)
        .where(NegotiationState.product_id == product.id)
        .where(NegotiationState.status == "active")
    )
    state = r.scalar_one_or_none()
    if state:
        return state
    list_price = float(product.harga or 0)
    cost = float(getattr(product, "cost_price", 0) or 0)
    floor = compute_floor_price(list_price, cost, policy)
    state = NegotiationState(
        seller_id=seller_id, conversation_id=conversation_id, product_id=product.id,
        list_price=list_price, floor_price=floor, current_offer=list_price, history_json=[],
    )
    db.add(state)
    await db.flush()
    return state


async def _phrase_offer(seller, product, decision, requires_approval: bool) -> str:
    """LLM merangkai kalimat di sekitar angka engine. Fallback jika LLM gagal/menyimpang."""
    from ai.agent import llm_client
    offer = decision["offer_price"]
    list_price = decision["list_price"]

    if requires_approval:
        fallback = f"Boleh kak 🙏 sebentar ya aku cek dulu ke owner buat harga spesial {product.nama}."
    elif decision["decision"] == "accept":
        fallback = f"Siap kak! {product.nama} aku kasih Rp {offer:,.0f} ya 😊 Lanjut order?"
    elif decision["decision"] == "counter_floor":
        fallback = (f"Maaf kak belum bisa segitu 🙏 tapi {product.nama} aku kasih harga terbaik "
                    f"Rp {offer:,.0f} (normal Rp {list_price:,.0f}). Gimana kak?")
    else:
        fallback = (f"Boleh nego kak 😊 {product.nama} aku kasih Rp {offer:,.0f} "
                    f"(normal Rp {list_price:,.0f}). Mau aku buatin ordernya?")

    prompt = [
        {"role": "system", "content": (
            "Kamu CS toko online Indonesia yang ramah. Tulis SATU balasan singkat (maks 2 kalimat) "
            "untuk situasi tawar-menawar. WAJIB memakai PERSIS angka rupiah yang diberikan, "
            "JANGAN mengarang angka lain. Bahasa santai, maksimal 1 emoji."
        )},
        {"role": "user", "content": (
            f"Produk: {product.nama}. Harga normal Rp {int(list_price)}. "
            f"Keputusan: {decision['decision']}. Harga yang ditawarkan ke pembeli: Rp {int(offer)}. "
            f"requires_approval={requires_approval}. Tulis balasannya."
        )},
    ]
    try:
        resp = await llm_client.chat.completions.create(
            model=settings.LLM_MODEL, messages=prompt, temperature=0.5, max_tokens=120,
        )
        text = (resp.choices[0].message.content or "").strip()
        # Guard angka: kalimat harus memuat harga engine, kalau tidak -> fallback
        flat = text.replace(".", "").replace(",", "")
        if requires_approval or str(int(offer)) in flat:
            return text or fallback
        return fallback
    except Exception as e:
        logger.warning(f"_phrase_offer LLM failed: {e}")
        return fallback


async def run_negotiation_turn(*, seller, conversation, message, history, db) -> dict:
    """
    Tangani satu giliran negosiasi. Menambah ke sesi (flush) — pemanggil yang commit.
    Return: {handled, reply, intent, stage, order_created, agent_run_id, approval_id}
    """
    policy = await get_or_create_policy(seller.id, db)
    if not policy.allow_auto_negotiation:
        return {"handled": False}

    product = await _resolve_focus_product(seller.id, conversation, history, message, db)
    if not product:
        return {"handled": False}  # tanpa produk fokus, biar Sales lama yang jawab

    state = await _get_or_create_state(seller.id, conversation.id, product, policy, db)
    customer_ask = parse_price_ask(message)
    decision = decide_offer(state.list_price, state.floor_price, customer_ask, state.rounds, policy)

    # Update state
    state.rounds += 1
    state.current_offer = decision["offer_price"]
    if customer_ask:
        state.last_customer_ask = customer_ask
    hist = list(state.history_json or [])
    hist.append({
        "round": state.rounds, "ask": customer_ask,
        "offer": decision["offer_price"], "decision": decision["decision"],
    })
    state.history_json = hist[-10:]
    if decision["decision"] == "accept":
        state.status = "accepted"

    # HITL approval bila perlu
    approval_id = None
    if decision["requires_approval"]:
        approval = AgentApproval(
            seller_id=seller.id, agent_role="negotiator", action_type="apply_discount",
            title=f"Diskon {decision['discount_pct']}% untuk {product.nama} (Rp {decision['offer_price']:,.0f})",
            detail_json={"product_id": product.id, **decision, "customer_ask": customer_ask},
            conversation_id=conversation.id, status="pending",
        )
        db.add(approval)
        await db.flush()
        approval_id = approval.id
        state.status = "escalated"

    reply = await _phrase_offer(seller, product, decision, decision["requires_approval"])

    run = AgentRun(
        seller_id=seller.id, agent_role="negotiator", trigger="chat",
        status="needs_approval" if decision["requires_approval"] else "done",
        summary=(f"Nego {product.nama}: minta Rp {int(customer_ask):,} → tawar Rp {decision['offer_price']:,} "
                 f"({decision['discount_pct']}%)" if customer_ask
                 else f"Nego {product.nama}: tawar Rp {decision['offer_price']:,}"),
        detail_json={"product": product.nama, **decision, "customer_ask": customer_ask},
        conversation_id=conversation.id,
    )
    db.add(run)
    await db.flush()

    return {
        "handled": True, "reply": reply, "intent": "order", "stage": "negotiation",
        "order_created": False, "agent_run_id": run.id, "approval_id": approval_id,
    }

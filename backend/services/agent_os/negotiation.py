"""
JUALIN OS — Mesin Negosiasi (Juru Tawar AI).

PRINSIP: ANGKA dikontrol fungsi deterministik (decide_offer), KATA dirangkai LLM,
lalu kalimat difirewall lagi (_text_price_safe). Dua lapis — tidak pernah jual rugi.
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
    r'\bboleh\s*\d{2,}', r'\bkalau\s*\d{2,}',
    r'\b\d+[.,]?\d*\s*(rb|ribu|k|jt|juta)\b',
    r'\b\d{2,}\s*aja\b',   # "100 aja" = nego; "2 aja" = kuantitas, bukan nego
    r'\bgocengan\b', r'\bsadis\b', r'\bharga\s*pas\b', r'\bnet\s*berapa\b',
    r'\bpaling\s*murah\b', r'\bbisa\s*goyang\b',
]


def is_negotiation(text: str) -> bool:
    """True jika pesan mengandung sinyal tawar-menawar."""
    t = (text or "").lower()
    return any(re.search(p, t) for p in _NEGO_PATTERNS)


_QTY_SUFFIX = r'(pcs|pc|biji|buah|unit|porsi|lusin|pasang|x)'


def parse_price_ask(text: str) -> float | None:
    """
    Ekstrak harga yang diminta customer (rupiah). None jika tidak ada.
    '150 ribu'/'150rb'/'150k' -> 150000 ; '1,5 juta'/'1.5jt' -> 1500000 ;
    'rp 150000' -> 150000 ; 'boleh 75?' -> 75000 ; 'ambil 2 pcs' -> None (kuantitas).
    """
    raw = (text or "").lower()
    # Nomor HP/rekening bukan harga: buang deret 8+ digit bila ada kata kunci kontak
    if re.search(r'\b(hp|wa|whatsapp|telp|telepon|no|nomor|rek|rekening)\b', raw):
        raw = re.sub(r'\+?\d{8,}', ' ', raw)
    # 'juta' ditangani SEBELUM pemisah ribuan dibuang ("1,5 juta" ≠ "15 juta")
    m = re.search(r'(\d+(?:[.,]\d{1,2})?)\s*(jt|juta)\b', raw)
    if m:
        return float(m.group(1).replace(",", ".")) * 1_000_000
    t = raw.replace(".", "").replace(",", "")
    m = re.search(r'(\d+)\s*(rb|ribu|k)\b', t)
    if m:
        return float(m.group(1)) * 1000
    m = re.search(r'rp\s*(\d{3,9})', t)
    if m:
        return float(m.group(1))
    m = re.search(r'\b(\d{4,9})\b', t)          # angka 4-9 digit = harga utuh
    if m:
        return float(m.group(1))
    # angka 2-3 digit = ribuan, KECUALI jelas kuantitas ("25 pcs")
    m = re.search(r'\b(\d{2,3})\b(?!\s*' + _QTY_SUFFIX + r'\b)', t)
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

    Concession ladder: ronde 0 -> 40% jalan dari list ke floor, ronde 1 -> 70%, ronde 2+ -> 100% (floor).
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
        offer, decision = customer_ask, "accept"
    elif customer_ask >= floor_price:
        offer, decision = concession_price, "counter"
    else:
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


# ── Firewall teks (lapis-2): kalimat TIDAK BOLEH memuat harga di bawah floor ──
_PRICE_IN_TEXT = re.compile(r'(?:rp\s*)?(\d[\d.,]*)\s*(rb|ribu|k|jt|juta)?\b', re.IGNORECASE)


def _extract_prices(text: str) -> list[float]:
    """Semua angka bergaya harga dalam teks, dinormalkan ke rupiah."""
    out = []
    for m in _PRICE_IN_TEXT.finditer(text or ""):
        try:
            v = float(m.group(1).replace(".", "").replace(",", ""))
        except ValueError:
            continue
        suf = (m.group(2) or "").lower()
        if suf in ("rb", "ribu", "k"):
            v *= 1000
        elif suf in ("jt", "juta"):
            v *= 1_000_000
        out.append(v)
    return out


def _text_price_safe(text: str, floor_price: float, offer_price: float) -> bool:
    """
    True bila teks memuat angka penawaran engine DAN tidak memuat harga < floor.
    ponytail: angka < 1000 dianggap bukan harga (qty/persen) — cukup untuk katalog rupiah UMKM.
    """
    prices = [p for p in _extract_prices(text) if p >= 1000]
    if any(p < floor_price - 0.5 for p in prices):
        return False
    return any(abs(p - offer_price) <= 1 for p in prices)


async def _resolve_focus_product(seller_id, conversation, history, message, db):
    """
    Produk fokus nego: (1) kontinuitas — nego aktif di percakapan ini;
    (2) pgvector DENGAN ambang jarak. Tanpa produk meyakinkan -> None
    (lebih baik Sales bertanya "produk yang mana kak?" daripada menawar produk salah).
    """
    r = await db.execute(
        select(NegotiationState)
        .where(NegotiationState.conversation_id == conversation.id)
        .where(NegotiationState.status == "active")
        .order_by(NegotiationState.id.desc())
        .limit(1)
    )
    st = r.scalar_one_or_none()
    if st and st.product_id:
        rp = await db.execute(select(Product).where(Product.id == st.product_id))
        p = rp.scalar_one_or_none()
        if p:
            return p

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
    try:
        from ai.embeddings import generate_embedding
        emb = generate_embedding(query)
        dist = Product.embedding.cosine_distance(emb)
        r = await db.execute(
            select(Product, dist.label("distance"))
            .where(Product.seller_id == seller_id)
            .where(Product.is_active == 1)
            .order_by(dist)
            .limit(1)
        )
        row = r.first()
    except Exception as e:
        logger.warning(f"focus product search failed: {e}")
        return None
    if not row:
        return None
    product, distance = row[0], float(row[1] if row[1] is not None else 1.0)
    if distance > settings.AGENT_OS_NEGO_MAX_DISTANCE:
        # ponytail: ambang dikalibrasi via env AGENT_OS_NEGO_MAX_DISTANCE — uji dengan katalog asli
        return None
    return product


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
    """LLM merangkai kalimat di sekitar angka engine, lalu difirewall. Fallback selalu siap."""
    offer = decision["offer_price"]
    list_price = decision["list_price"]

    if requires_approval:
        # JANGAN panggil LLM di sini: tidak boleh ada angka yang belum di-ACC owner terucap.
        return f"Boleh kak 🙏 sebentar ya, aku cek dulu ke owner buat harga spesial {product.nama}."

    if decision["decision"] == "accept":
        fallback = (f"Deal ya kak! {product.nama} jadi Rp {offer:,.0f} 🤝 "
                    f"Ketik Nama / Alamat / No HP, langsung aku buatkan ordernya.")
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
            f"Tulis balasannya."
        )},
    ]
    try:
        from ai.agent import llm_client
        resp = await llm_client.chat.completions.create(
            model=settings.LLM_MODEL, messages=prompt, temperature=0.5, max_tokens=120,
        )
        text = (resp.choices[0].message.content or "").strip()
        if text and _text_price_safe(text, decision["floor_price"], offer):
            return text
        return fallback
    except Exception as e:
        logger.warning(f"_phrase_offer LLM failed: {e}")
        return fallback


# ── Deal → Order: dipakai oleh KEDUA jalur pembuatan order ──

async def apply_deal_prices(seller_id: int, conversation_id: int | None,
                            items: list[dict], db: AsyncSession) -> list[NegotiationState]:
    """
    Hormati harga deal nego 'accepted' pada item yang cocok (mutasi items in-place).
    Return: daftar state yang dipakai (tandai fulfilled setelah order berhasil).
    ponytail: tanpa kedaluwarsa — deal terikat percakapan, cukup untuk skala demo/UMKM.
    """
    if not conversation_id or not items:
        return []
    r = await db.execute(
        select(NegotiationState)
        .where(NegotiationState.seller_id == seller_id)
        .where(NegotiationState.conversation_id == conversation_id)
        .where(NegotiationState.status == "accepted")
    )
    states = {s.product_id: s for s in r.scalars().all()}
    used = []
    for it in items:
        s = states.get(it.get("product_id"))
        if s and s.current_offer and 0 < float(s.current_offer) < float(it.get("harga") or 0):
            it["harga_asli"] = it.get("harga")
            it["harga"] = float(s.current_offer)
            it["nego"] = True
            used.append(s)
    return used


def mark_deals_fulfilled(states: list, order_id: int) -> None:
    """Tandai deal sudah ditunaikan jadi order (panggil SETELAH order sukses dibuat)."""
    for s in states or []:
        s.status = "fulfilled"
        h = list(s.history_json or [])
        h.append({"order_id": order_id})
        s.history_json = h[-10:]


async def get_deal_context(seller_id: int, conversation_id: int, db: AsyncSession) -> str:
    """Konteks system prompt: harga yang SUDAH deal di percakapan ini (agar LLM tidak sebut harga katalog)."""
    r = await db.execute(
        select(NegotiationState)
        .where(NegotiationState.seller_id == seller_id)
        .where(NegotiationState.conversation_id == conversation_id)
        .where(NegotiationState.status == "accepted")
    )
    lines = []
    for s in r.scalars().all():
        rp = await db.execute(select(Product).where(Product.id == s.product_id))
        p = rp.scalar_one_or_none()
        if p and s.current_offer:
            lines.append(f"- {p.nama}: SUDAH DEAL di Rp {float(s.current_offer):,.0f} (JANGAN pakai harga katalog)")
    if not lines:
        return ""
    return "\n\n⚠️ DEAL NEGOSIASI AKTIF DI PERCAKAPAN INI:\n" + "\n".join(lines)


async def run_negotiation_turn(*, seller, conversation, message, history, db) -> dict:
    """
    Tangani satu giliran negosiasi. Menambah ke sesi (flush) — pemanggil yang commit.
    Return: {handled, reply, intent, stage, order_created, agent_run_id, approval_id, nego}
    """
    policy = await get_or_create_policy(seller.id, db)
    if not policy.allow_auto_negotiation:
        return {"handled": False}

    product = await _resolve_focus_product(seller.id, conversation, history, message, db)
    if not product:
        return {"handled": False}  # tanpa produk fokus yang meyakinkan, biar Sales yang jawab

    state = await _get_or_create_state(seller.id, conversation.id, product, policy, db)
    customer_ask = parse_price_ask(message)
    decision = decide_offer(state.list_price, state.floor_price, customer_ask, state.rounds, policy)

    # Tingkat otonomi menentukan kapan butuh ACC owner (sebelumnya kolom ini tidak pernah dibaca!)
    requires_approval = decision["requires_approval"]
    if policy.autonomy_level == "full_auto":
        requires_approval = False
    elif policy.autonomy_level == "assist":
        requires_approval = True
    decision["requires_approval"] = requires_approval

    # Update state
    state.rounds += 1
    state.current_offer = decision["offer_price"]
    if customer_ask:
        state.last_customer_ask = customer_ask
    hist = list(state.history_json or [])
    hist.append({
        "round": state.rounds, "ask": customer_ask,
        "offer": decision["offer_price"], "decision": decision["decision"],
        "requires_approval": requires_approval,
    })
    state.history_json = hist[-10:]

    approval_id = None
    if requires_approval:
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
    elif decision["decision"] == "accept":
        state.status = "accepted"

    reply = await _phrase_offer(seller, product, decision, requires_approval)

    run = AgentRun(
        seller_id=seller.id, agent_role="negotiator", trigger="chat",
        status="needs_approval" if requires_approval else "done",
        summary=(f"Nego {product.nama}: minta Rp {int(customer_ask):,} → tawar Rp {decision['offer_price']:,} "
                 f"({decision['discount_pct']}%)" if customer_ask
                 else f"Nego {product.nama}: tawar Rp {decision['offer_price']:,}"),
        detail_json={"product": product.nama, "product_id": product.id, **decision,
                     "customer_ask": customer_ask},
        conversation_id=conversation.id,
    )
    db.add(run)
    await db.flush()

    return {
        "handled": True, "reply": reply, "intent": "order", "stage": "negotiation",
        "order_created": False, "agent_run_id": run.id, "approval_id": approval_id,
        # Payload badge untuk UI PEMBELI — sengaja TANPA floor_price (rahasia dapur seller!)
        "nego": {
            "product": product.nama,
            "decision": decision["decision"],
            "offer_price": decision["offer_price"],
            "discount_pct": decision["discount_pct"],
            "round": decision["round"],
            "requires_approval": requires_approval,
        },
    }

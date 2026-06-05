"""
Sales Playbook, Customer Scoring, Dynamic Offer, Knowledge Base, QA Review, Experiment endpoints.
Consolidated route file for Plan C features.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime, timezone

from models.database import get_db
from models.user import User
from api.routes_auth import get_current_user

router = APIRouter()

ALLOWED_OFFER_TYPES = {"fixed_discount", "free_shipping", "bundle", "urgency"}
ALLOWED_OFFER_VALUE_TYPES = {"fixed", "percent"}
ALLOWED_KNOWLEDGE_TYPES = {"manual", "faq", "policy", "product_note", "import_note"}
ALLOWED_EXPERIMENT_TYPES = {"prompt", "campaign_cta", "storefront_cta", "offer_wording"}


def _normalize_experiment_variants(variants: list | None) -> list[dict]:
    if not variants:
        return [
            {"name": "Control", "content": "", "weight": 50},
            {"name": "Variant B", "content": "", "weight": 50},
        ]
    if len(variants) > 6:
        raise HTTPException(status_code=400, detail="Maksimal 6 variant per experiment")

    normalized = []
    for raw in variants:
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="Variant experiment harus berupa object")
        name = str(raw.get("name", "")).strip()[:100]
        content = str(raw.get("content", ""))[:10000]
        try:
            weight = int(raw.get("weight", 50))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Weight variant harus berupa angka")
        if not name:
            raise HTTPException(status_code=400, detail="Nama variant wajib diisi")
        if weight < 0 or weight > 100:
            raise HTTPException(status_code=400, detail="Weight variant harus 0-100")
        normalized.append({"name": name, "content": content, "weight": weight})
    return normalized


# ══════════════════════════════════════════════════
# Sales Playbook
# ══════════════════════════════════════════════════

@router.get("/playbooks")
async def list_playbooks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.playbook import SalesPlaybook
    result = await db.execute(
        select(SalesPlaybook).where(SalesPlaybook.seller_id == current_user.id)
        .order_by(SalesPlaybook.priority.desc())
    )
    playbooks = result.scalars().all()

    # If no playbooks, seed defaults
    if not playbooks:
        defaults = [
            {"key": "first_time_buyer", "name": "Pembeli Pertama", "description": "Sapaan hangat dan panduan belanja untuk customer baru", "prompt_instructions": "Treat this customer as a first-time visitor. Be extra welcoming, explain how to order, and suggest best sellers.", "priority": 60},
            {"key": "price_sensitive", "name": "Sensitive Harga", "description": "Negosiasi halus, tawarkan bundle dan promo", "prompt_instructions": "Customer may be price-conscious. Emphasize value, suggest bundles, mention ongoing promotions.", "priority": 50},
            {"key": "repeat_buyer", "name": "Pelanggan Setia", "description": "Apresiasi dan rekomendasi produk baru", "prompt_instructions": "This is a returning customer. Thank them for loyalty, recommend new products, offer repeat buyer benefits.", "priority": 40},
            {"key": "abandoned_payment", "name": "Payment Tertunda", "description": "Follow-up halus untuk pembayaran pending", "prompt_instructions": "Customer has a pending payment. Gently remind and offer help with payment process.", "priority": 70},
            {"key": "complaint_recovery", "name": "Penanganan Keluhan", "description": "Empati, solusi cepat, dan recovery", "prompt_instructions": "Customer seems frustrated or has a complaint. Be empathetic, acknowledge the issue, offer a solution quickly.", "priority": 80},
            {"key": "product_education", "name": "Edukasi Produk", "description": "Jelaskan produk secara detail dan persuasif", "prompt_instructions": "Customer is asking about product details. Provide thorough explanation, use cases, and comparisons.", "priority": 30},
        ]
        for d in defaults:
            pb = SalesPlaybook(seller_id=current_user.id, **d)
            db.add(pb)
        await db.commit()
        return await list_playbooks(current_user=current_user, db=db)

    return [
        {
            "id": p.id, "key": p.key, "name": p.name, "description": p.description,
            "is_enabled": p.is_enabled, "priority": p.priority, "tone": p.tone,
        }
        for p in playbooks
    ]


class PlaybookUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    priority: Optional[int] = Field(default=None, ge=0, le=100)
    tone: Optional[str] = Field(default=None, max_length=50)


@router.patch("/playbooks/{playbook_id}")
async def update_playbook(
    playbook_id: int,
    req: PlaybookUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.playbook import SalesPlaybook
    result = await db.execute(
        select(SalesPlaybook)
        .where(SalesPlaybook.id == playbook_id, SalesPlaybook.seller_id == current_user.id)
    )
    pb = result.scalar_one_or_none()
    if not pb:
        raise HTTPException(status_code=404, detail="Playbook tidak ditemukan")

    if req.is_enabled is not None:
        pb.is_enabled = req.is_enabled
    if req.priority is not None:
        pb.priority = req.priority
    if req.tone is not None:
        pb.tone = req.tone
    await db.commit()
    return {"message": f"Playbook '{pb.name}' updated"}


# ══════════════════════════════════════════════════
# Customer Scoring
# ══════════════════════════════════════════════════

@router.get("/customers/{customer_id}/score")
async def get_customer_score(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.customer_score import CustomerScore
    result = await db.execute(
        select(CustomerScore)
        .where(CustomerScore.customer_id == customer_id, CustomerScore.seller_id == current_user.id)
    )
    score = result.scalar_one_or_none()
    if not score:
        # Compute on-demand
        score = await _compute_customer_score(db, customer_id, current_user.id)

    return {
        "customer_id": score.customer_id,
        "overall_score": score.overall_score,
        "tier": score.tier,
        "purchase_likelihood": score.purchase_likelihood,
        "repeat_likelihood": score.repeat_likelihood,
        "churn_risk": score.churn_risk,
        "value_score": score.value_score,
        "support_risk": score.support_risk,
        "reason_codes": score.reason_codes,
        "computed_at": score.computed_at.isoformat() if score.computed_at else "",
    }


@router.post("/customers/recompute-scores")
async def recompute_all_scores(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.crm import Customer
    result = await db.execute(
        select(Customer.id).where(Customer.seller_id == current_user.id)
    )
    customer_ids = [row[0] for row in result.all()]
    count = 0
    for cid in customer_ids[:200]:  # limit batch
        try:
            await _compute_customer_score(db, cid, current_user.id)
            count += 1
        except Exception:
            pass
    await db.commit()
    return {"message": f"Recomputed scores for {count} customers"}


async def _compute_customer_score(db: AsyncSession, customer_id: int, seller_id: int):
    """Compute customer score from real events."""
    from models.customer_score import CustomerScore
    from models.crm import Customer, CustomerEvent
    from models.order import Order, OrderStatus
    from models.conversation import Conversation

    customer_result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.seller_id == seller_id)
    )
    customer = customer_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")

    # Get or create score
    result = await db.execute(
        select(CustomerScore)
        .where(CustomerScore.customer_id == customer_id, CustomerScore.seller_id == seller_id)
    )
    score = result.scalar_one_or_none()
    if not score:
        score = CustomerScore(customer_id=customer_id, seller_id=seller_id)
        db.add(score)

    reasons = []
    signals = {}

    # Order history
    order_query = select(func.count(Order.id)).where(Order.seller_id == seller_id)
    paid_query = select(func.count(Order.id)).where(Order.seller_id == seller_id, Order.status == OrderStatus.PAID)
    spent_query = select(func.coalesce(func.sum(Order.total), 0)).where(Order.seller_id == seller_id, Order.status == OrderStatus.PAID)
    if customer.phone:
        order_query = order_query.where(Order.customer_phone == customer.phone)
        paid_query = paid_query.where(Order.customer_phone == customer.phone)
        spent_query = spent_query.where(Order.customer_phone == customer.phone)
    else:
        order_query = order_query.where(Order.customer_name == customer.name)
        paid_query = paid_query.where(Order.customer_name == customer.name)
        spent_query = spent_query.where(Order.customer_name == customer.name)

    orders_result = await db.execute(order_query)
    order_count = orders_result.scalar() or 0
    signals["order_count"] = order_count

    paid_result = await db.execute(paid_query)
    paid_count = paid_result.scalar() or 0
    signals["paid_count"] = paid_count
    spent_result = await db.execute(spent_query)
    total_spent = float(spent_result.scalar() or customer.total_spent or 0)
    signals["total_spent"] = total_spent

    # Chat recency
    chat_query = select(func.count(Conversation.id)).where(Conversation.seller_id == seller_id)
    if customer.session_id:
        chat_query = chat_query.where(Conversation.session_id == customer.session_id)
    elif customer.phone:
        chat_query = chat_query.where(Conversation.customer_phone == customer.phone)
    else:
        chat_query = chat_query.where(Conversation.customer_name == customer.name)
    chat_result = await db.execute(chat_query)
    chat_count = chat_result.scalar() or 0
    signals["chat_count"] = chat_count

    event_result = await db.execute(
        select(func.count(CustomerEvent.id))
        .where(CustomerEvent.seller_id == seller_id, CustomerEvent.customer_id == customer_id)
    )
    event_count = event_result.scalar() or 0
    signals["event_count"] = event_count

    recency_bonus = 0
    if customer.last_seen_at:
        last_seen = customer.last_seen_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        days_since_seen = max(0, (datetime.now(timezone.utc) - last_seen).days)
        signals["days_since_seen"] = days_since_seen
        recency_bonus = max(0, 30 - days_since_seen)

    # Compute scores
    score.purchase_likelihood = min(100, (chat_count * 10) + (event_count * 5) + recency_bonus + (order_count * 20))
    if chat_count > 0:
        reasons.append({"code": "active_chatter", "label": "Aktif berkomunikasi", "impact": 15})
    if recency_bonus:
        reasons.append({"code": "recent_activity", "label": "Baru berinteraksi", "impact": recency_bonus})

    score.repeat_likelihood = min(100, paid_count * 30)
    if paid_count >= 2:
        reasons.append({"code": "repeat_buyer", "label": "Pernah beli 2+ kali", "impact": 30})

    score.churn_risk = max(0, 70 - recency_bonus - (chat_count * 5) - (paid_count * 15))
    if score.churn_risk > 60:
        reasons.append({"code": "high_churn", "label": "Risiko churn tinggi", "impact": -20})

    score.value_score = min(100, (paid_count * 20) + min(40, total_spent / 100000 * 5))
    score.support_risk = 20 if chat_count > 10 else 5

    # Overall
    score.overall_score = round(
        (score.purchase_likelihood * 0.3 + score.repeat_likelihood * 0.25 +
         (100 - score.churn_risk) * 0.2 + score.value_score * 0.2 +
         (100 - score.support_risk) * 0.05), 1
    )

    # Tier
    if score.overall_score >= 70:
        score.tier = "hot"
    elif score.overall_score >= 40:
        score.tier = "warm"
    else:
        score.tier = "cold"

    score.reason_codes = reasons
    score.input_signals = signals
    score.computed_at = datetime.now(timezone.utc)
    await db.flush()
    return score


# ══════════════════════════════════════════════════
# Dynamic Offer Engine
# ══════════════════════════════════════════════════

class OfferCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: str = Field(default="fixed_discount", max_length=30)
    value: float = Field(default=0, ge=0, le=1_000_000_000)
    value_type: str = Field(default="fixed", max_length=20)
    min_order_value: float = Field(default=0, ge=0, le=1_000_000_000)
    allow_chat_auto: bool = False


@router.post("/offers")
async def create_offer(
    req: OfferCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.offer import Offer
    if req.type not in ALLOWED_OFFER_TYPES:
        raise HTTPException(status_code=400, detail="Tipe offer tidak valid")
    if req.value_type not in ALLOWED_OFFER_VALUE_TYPES:
        raise HTTPException(status_code=400, detail="Value type offer tidak valid")
    if req.value_type == "percent" and req.value > 100:
        raise HTTPException(status_code=400, detail="Diskon persen tidak boleh lebih dari 100")

    offer = Offer(
        seller_id=current_user.id,
        name=req.name, type=req.type, value=req.value,
        value_type=req.value_type, min_order_value=req.min_order_value,
        allow_chat_auto=req.allow_chat_auto,
    )
    db.add(offer)
    await db.commit()
    return {"id": offer.id, "name": offer.name, "message": "Offer created"}


@router.get("/offers")
async def list_offers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.offer import Offer
    result = await db.execute(
        select(Offer).where(Offer.seller_id == current_user.id)
        .order_by(Offer.created_at.desc()).limit(50)
    )
    return [
        {
            "id": o.id, "name": o.name, "type": o.type, "value": o.value,
            "value_type": o.value_type, "is_active": o.is_active,
            "current_redemptions": o.current_redemptions,
            "allow_chat_auto": o.allow_chat_auto,
        }
        for o in result.scalars().all()
    ]


@router.get("/offers/recommendations")
async def offer_recommendations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.offer import OfferRecommendation
    result = await db.execute(
        select(OfferRecommendation).where(OfferRecommendation.seller_id == current_user.id)
        .order_by(OfferRecommendation.created_at.desc()).limit(20)
    )
    return [
        {
            "id": r.id, "trigger_type": r.trigger_type,
            "customer_segment": r.customer_segment,
            "estimated_impact": r.estimated_impact, "status": r.status,
        }
        for r in result.scalars().all()
    ]


@router.post("/offers/recommendations/{rec_id}/approve")
async def approve_offer_recommendation(
    rec_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.offer import OfferRecommendation
    result = await db.execute(
        select(OfferRecommendation)
        .where(OfferRecommendation.id == rec_id, OfferRecommendation.seller_id == current_user.id)
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation tidak ditemukan")
    rec.status = "approved"
    await db.commit()
    return {"message": "Offer recommendation approved"}


# ══════════════════════════════════════════════════
# Knowledge Base / RAG
# ══════════════════════════════════════════════════

class KnowledgeSourceCreate(BaseModel):
    type: str = Field(default="manual", max_length=30)
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(default="", max_length=100000)


@router.post("/knowledge/sources")
async def create_knowledge_source(
    req: KnowledgeSourceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.knowledge import KnowledgeSource, KnowledgeChunk
    if req.type not in ALLOWED_KNOWLEDGE_TYPES:
        raise HTTPException(status_code=400, detail="Tipe knowledge source tidak valid")

    source = KnowledgeSource(
        seller_id=current_user.id, type=req.type,
        title=req.title, content=req.content,
    )
    db.add(source)
    await db.flush()

    # Auto-chunk content
    if req.content:
        chunks = _chunk_text(req.content)
        for i, chunk_text in enumerate(chunks):
            chunk = KnowledgeChunk(
                source_id=source.id, seller_id=current_user.id,
                content=chunk_text, chunk_index=i, token_count=len(chunk_text.split()),
            )
            db.add(chunk)
        source.chunk_count = len(chunks)

    await db.commit()
    return {"id": source.id, "chunk_count": source.chunk_count, "message": "Knowledge source created"}


def _chunk_text(text: str, max_tokens: int = 300) -> list:
    """Split text into chunks of ~max_tokens words."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), max_tokens):
        chunk = " ".join(words[i:i + max_tokens])
        if chunk.strip():
            chunks.append(chunk.strip())
    return chunks or [text]


@router.get("/knowledge/sources")
async def list_knowledge_sources(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.knowledge import KnowledgeSource
    result = await db.execute(
        select(KnowledgeSource).where(KnowledgeSource.seller_id == current_user.id)
        .order_by(KnowledgeSource.created_at.desc())
    )
    return [
        {
            "id": s.id, "type": s.type, "title": s.title, "status": s.status,
            "chunk_count": s.chunk_count,
            "created_at": s.created_at.isoformat() if s.created_at else "",
        }
        for s in result.scalars().all()
    ]


@router.post("/knowledge/sources/{source_id}/reindex")
async def reindex_knowledge_source(
    source_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.knowledge import KnowledgeSource, KnowledgeChunk
    result = await db.execute(
        select(KnowledgeSource)
        .where(KnowledgeSource.id == source_id, KnowledgeSource.seller_id == current_user.id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source tidak ditemukan")

    # Delete old chunks
    old_chunks = await db.execute(
        select(KnowledgeChunk).where(KnowledgeChunk.source_id == source.id)
    )
    for c in old_chunks.scalars().all():
        await db.delete(c)

    # Re-chunk
    if source.content:
        chunks = _chunk_text(source.content)
        for i, chunk_text in enumerate(chunks):
            chunk = KnowledgeChunk(
                source_id=source.id, seller_id=current_user.id,
                content=chunk_text, chunk_index=i, token_count=len(chunk_text.split()),
            )
            db.add(chunk)
        source.chunk_count = len(chunks)
    source.status = "active"
    await db.commit()
    return {"message": "Reindexed", "chunk_count": source.chunk_count}


@router.delete("/knowledge/sources/{source_id}")
async def delete_knowledge_source(
    source_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.knowledge import KnowledgeSource, KnowledgeChunk
    result = await db.execute(
        select(KnowledgeSource)
        .where(KnowledgeSource.id == source_id, KnowledgeSource.seller_id == current_user.id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source tidak ditemukan")

    chunks = await db.execute(
        select(KnowledgeChunk).where(KnowledgeChunk.source_id == source.id)
    )
    for c in chunks.scalars().all():
        await db.delete(c)
    await db.delete(source)
    await db.commit()
    return {"message": "Knowledge source deleted"}


# ══════════════════════════════════════════════════
# QA Review Queue
# ══════════════════════════════════════════════════

@router.get("/qa-review")
async def list_qa_reviews(
    status: str = "pending",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.qa_review import QAReviewItem
    query = select(QAReviewItem).where(QAReviewItem.seller_id == current_user.id)
    if status:
        query = query.where(QAReviewItem.status == status)
    query = query.order_by(QAReviewItem.created_at.desc()).limit(50)
    result = await db.execute(query)
    return [
        {
            "id": r.id, "type": r.type, "status": r.status, "priority": r.priority,
            "original_content": r.original_content[:200] if r.original_content else "",
            "reason": r.reason,
            "thread_id": r.thread_id, "order_id": r.order_id,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in result.scalars().all()
    ]


class QAReviewAction(BaseModel):
    notes: str = Field(default="", max_length=2000)
    edited_content: str = Field(default="", max_length=10000)


@router.post("/qa-review/{item_id}/approve")
async def approve_qa_review(
    item_id: int,
    req: QAReviewAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.qa_review import QAReviewItem
    result = await db.execute(
        select(QAReviewItem)
        .where(QAReviewItem.id == item_id, QAReviewItem.seller_id == current_user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item tidak ditemukan")
    item.status = "approved"
    item.reviewer_notes = req.notes
    item.reviewed_by = current_user.id
    item.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "QA item approved"}


@router.post("/qa-review/{item_id}/reject")
async def reject_qa_review(
    item_id: int,
    req: QAReviewAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.qa_review import QAReviewItem
    result = await db.execute(
        select(QAReviewItem)
        .where(QAReviewItem.id == item_id, QAReviewItem.seller_id == current_user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item tidak ditemukan")
    item.status = "rejected"
    item.reviewer_notes = req.notes
    item.reviewed_by = current_user.id
    item.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "QA item rejected"}


@router.post("/qa-review/{item_id}/edit-and-send")
async def edit_and_send_qa_review(
    item_id: int,
    req: QAReviewAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.qa_review import QAReviewItem
    result = await db.execute(
        select(QAReviewItem)
        .where(QAReviewItem.id == item_id, QAReviewItem.seller_id == current_user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item tidak ditemukan")
    if not req.edited_content:
        raise HTTPException(status_code=400, detail="Edited content wajib diisi")
    item.status = "edited"
    item.edited_content = req.edited_content
    item.reviewer_notes = req.notes
    item.reviewed_by = current_user.id
    item.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "QA item edited and marked for send"}


# ══════════════════════════════════════════════════
# Experimentation
# ══════════════════════════════════════════════════

class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: str = Field(default="prompt", max_length=50)
    description: str = Field(default="", max_length=5000)
    variants: list = Field(default_factory=list, max_length=6)


@router.post("/experiments")
async def create_experiment(
    req: ExperimentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.experiment import Experiment, ExperimentVariant
    if req.type not in ALLOWED_EXPERIMENT_TYPES:
        raise HTTPException(status_code=400, detail="Tipe experiment tidak valid")

    exp = Experiment(
        seller_id=current_user.id, name=req.name,
        type=req.type, description=req.description,
    )
    db.add(exp)
    await db.flush()

    for v in _normalize_experiment_variants(req.variants):
        variant = ExperimentVariant(
            experiment_id=exp.id, name=v.get("name", ""),
            content=v.get("content", ""), weight=v.get("weight", 50),
        )
        db.add(variant)
    await db.commit()
    return {"id": exp.id, "name": exp.name, "message": "Experiment created"}


@router.get("/experiments")
async def list_experiments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.experiment import Experiment
    result = await db.execute(
        select(Experiment).where(Experiment.seller_id == current_user.id)
        .order_by(Experiment.created_at.desc()).limit(50)
    )
    return [
        {
            "id": e.id, "name": e.name, "type": e.type, "status": e.status,
            "description": e.description,
            "started_at": e.started_at.isoformat() if e.started_at else None,
            "stopped_at": e.stopped_at.isoformat() if e.stopped_at else None,
        }
        for e in result.scalars().all()
    ]


@router.post("/experiments/{exp_id}/start")
async def start_experiment(
    exp_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.experiment import Experiment
    result = await db.execute(
        select(Experiment).where(Experiment.id == exp_id, Experiment.seller_id == current_user.id)
    )
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment tidak ditemukan")
    exp.status = "running"
    exp.started_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": f"Experiment '{exp.name}' started"}


@router.post("/experiments/{exp_id}/stop")
async def stop_experiment(
    exp_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.experiment import Experiment
    result = await db.execute(
        select(Experiment).where(Experiment.id == exp_id, Experiment.seller_id == current_user.id)
    )
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment tidak ditemukan")
    exp.status = "stopped"
    exp.stopped_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": f"Experiment '{exp.name}' stopped"}


@router.get("/experiments/{exp_id}/results")
async def experiment_results(
    exp_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.experiment import Experiment, ExperimentVariant
    result = await db.execute(
        select(Experiment).where(Experiment.id == exp_id, Experiment.seller_id == current_user.id)
    )
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment tidak ditemukan")

    variants_result = await db.execute(
        select(ExperimentVariant).where(ExperimentVariant.experiment_id == exp.id)
    )
    variants = variants_result.scalars().all()

    return {
        "experiment": {"id": exp.id, "name": exp.name, "status": exp.status, "type": exp.type},
        "variants": [
            {
                "id": v.id, "name": v.name, "weight": v.weight,
                "impressions": v.impressions, "conversions": v.conversions,
                "revenue": v.revenue,
                "conversion_rate": round(v.conversions / v.impressions * 100, 1) if v.impressions > 0 else 0,
            }
            for v in variants
        ],
    }

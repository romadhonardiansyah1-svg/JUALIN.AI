"""JUALIN OS — API routes untuk Pusat Komando AI Crew."""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import get_db
from models.user import User
from models.agent_os import AgentPolicy, AgentRun, AgentApproval, NegotiationState, AGENT_ROLES
from api.routes_auth import get_current_user
from core.audit import record_audit
from services.agent_os.policy import get_or_create_policy
from models.conversation import Message, MessageRole
from services.agent_os.finance import build_finance_snapshot
from services.agent_os.brief import build_daily_brief

router = APIRouter()


def _run_dict(r: AgentRun) -> dict:
    return {
        "id": r.id, "agent_role": r.agent_role, "trigger": r.trigger, "status": r.status,
        "summary": r.summary, "detail": r.detail_json or {},
        "conversation_id": r.conversation_id, "order_id": r.order_id,
        "created_at": r.created_at.isoformat() if r.created_at else "",
    }


@router.get("/overview")
async def overview(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    r = await db.execute(
        select(AgentRun.agent_role, func.count(AgentRun.id))
        .where(AgentRun.seller_id == current_user.id)
        .where(AgentRun.created_at >= since)
        .group_by(AgentRun.agent_role)
    )
    by_role = {role: int(cnt) for role, cnt in r.all()}

    pa = await db.execute(
        select(func.count(AgentApproval.id))
        .where(AgentApproval.seller_id == current_user.id)
        .where(AgentApproval.status == "pending")
    )
    pending_approvals = int(pa.scalar() or 0)

    finance = await build_finance_snapshot(current_user.id, db)

    crew = []
    labels = {
        "orchestrator": "Manajer AI", "sales": "Pramuniaga", "negotiator": "Juru Tawar",
        "inventory": "Gudang", "growth": "Marketing", "finance": "Keuangan", "cs": "Layanan",
    }
    for role in AGENT_ROLES:
        crew.append({
            "role": role, "label": labels.get(role, role),
            "actions_24h": by_role.get(role, 0),
            "active": True,
        })
    return {
        "crew": crew,
        "activity_by_role": by_role,
        "pending_approvals": pending_approvals,
        "finance": finance,
    }


@router.get("/activity")
async def activity(limit: int = 30, current_user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    limit = max(1, min(limit, 100))
    r = await db.execute(
        select(AgentRun).where(AgentRun.seller_id == current_user.id)
        .order_by(desc(AgentRun.id)).limit(limit)
    )
    return [_run_dict(x) for x in r.scalars().all()]


@router.get("/brief")
async def brief(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    data = await build_daily_brief(current_user.id, db)
    await db.commit()
    return data


@router.get("/policy")
async def get_policy(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = await get_or_create_policy(current_user.id, db)
    await db.commit()
    return {
        "autonomy_level": p.autonomy_level,
        "allow_auto_negotiation": p.allow_auto_negotiation,
        "allow_auto_followup": p.allow_auto_followup,
        "allow_low_stock_alert": p.allow_low_stock_alert,
        "daily_brief_enabled": p.daily_brief_enabled,
        "max_discount_percent": p.max_discount_percent,
        "margin_floor_percent": p.margin_floor_percent,
        "require_approval_above_percent": p.require_approval_above_percent,
        "nego_max_rounds": p.nego_max_rounds,
        "low_stock_threshold": p.low_stock_threshold,
    }


class PolicyUpdate(BaseModel):
    autonomy_level: str | None = None
    allow_auto_negotiation: bool | None = None
    allow_auto_followup: bool | None = None
    allow_low_stock_alert: bool | None = None
    daily_brief_enabled: bool | None = None
    max_discount_percent: float | None = None
    margin_floor_percent: float | None = None
    require_approval_above_percent: float | None = None
    nego_max_rounds: int | None = None
    low_stock_threshold: int | None = None


@router.patch("/policy")
async def update_policy(body: PolicyUpdate, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    p = await get_or_create_policy(current_user.id, db)
    if body.autonomy_level is not None:
        if body.autonomy_level not in ("assist", "auto_with_approval", "full_auto"):
            raise HTTPException(status_code=400, detail="autonomy_level tidak valid")
        p.autonomy_level = body.autonomy_level
    for field in ("allow_auto_negotiation", "allow_auto_followup", "allow_low_stock_alert", "daily_brief_enabled"):
        val = getattr(body, field)
        if val is not None:
            setattr(p, field, bool(val))
    for field, lo, hi in (("max_discount_percent", 0, 90), ("margin_floor_percent", 0, 90),
                          ("require_approval_above_percent", 0, 90)):
        val = getattr(body, field)
        if val is not None:
            setattr(p, field, max(lo, min(float(val), hi)))
    if body.nego_max_rounds is not None:
        p.nego_max_rounds = max(1, min(int(body.nego_max_rounds), 6))
    if body.low_stock_threshold is not None:
        p.low_stock_threshold = max(0, min(int(body.low_stock_threshold), 100))
    await db.commit()
    return {"success": True}


@router.get("/approvals")
async def list_approvals(status: str = "pending", current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    q = select(AgentApproval).where(AgentApproval.seller_id == current_user.id)
    if status:
        q = q.where(AgentApproval.status == status)
    q = q.order_by(desc(AgentApproval.id)).limit(50)
    r = await db.execute(q)
    return [
        {
            "id": a.id, "agent_role": a.agent_role, "action_type": a.action_type,
            "title": a.title, "detail": a.detail_json or {}, "status": a.status,
            "conversation_id": a.conversation_id,
            "created_at": a.created_at.isoformat() if a.created_at else "",
        }
        for a in r.scalars().all()
    ]


async def _decide_approval(approval_id: int, decision: str, current_user: User, db: AsyncSession):
    r = await db.execute(
        select(AgentApproval).where(AgentApproval.id == approval_id)
        .where(AgentApproval.seller_id == current_user.id)
    )
    a = r.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Approval tidak ditemukan")
    if a.status != "pending":
        return {"success": True, "already": a.status}
    a.status = decision
    a.decided_by = current_user.id
    a.decided_at = datetime.now(timezone.utc)

    # ── RESUME percakapan: kabari pembeli + update NegotiationState ──
    followup_text = None
    detail = a.detail_json or {}
    offer = detail.get("offer_price")
    pid = detail.get("product_id")
    if a.action_type == "apply_discount" and a.conversation_id:
        rs = await db.execute(
            select(NegotiationState)
            .where(NegotiationState.conversation_id == a.conversation_id)
            .where(NegotiationState.product_id == pid)
            .order_by(desc(NegotiationState.id))
            .limit(1)
        )
        state = rs.scalar_one_or_none()
        if decision == "approved" and offer:
            if state:
                state.status = "accepted"
                state.current_offer = float(offer)
            followup_text = (
                f"Kabar baik kak, owner sudah ACC ✅ jadi Rp {float(offer):,.0f} ya! "
                f"Ketik Nama / Alamat / No HP, langsung aku buatkan ordernya 🙌"
            )
        elif decision == "rejected":
            policy = await get_or_create_policy(current_user.id, db)
            safe = None
            if state:
                thr_price = float(state.list_price) * (1 - policy.require_approval_above_percent / 100.0)
                safe = round(max(float(state.floor_price), thr_price))
                state.status = "active"
                state.current_offer = safe
            if safe:
                followup_text = (
                    f"Maaf kak, untuk harga itu owner belum bisa 🙏 "
                    f"Tapi aku masih bisa kasih Rp {safe:,.0f} — gimana kak?"
                )
            else:
                followup_text = "Maaf kak, untuk harga itu owner belum bisa 🙏 Harga terbaik tetap penawaranku sebelumnya ya 😊"
        if followup_text:
            db.add(Message(conversation_id=a.conversation_id, role=MessageRole.AI, content=followup_text))

    db.add(AgentRun(
        seller_id=current_user.id, agent_role="negotiator", trigger="manual", status="done",
        summary=f"Persetujuan {decision}: {a.title}",
        detail_json={"approval_id": a.id, "followup_sent": bool(followup_text)},
        conversation_id=a.conversation_id,
    ))
    await record_audit(
        db, action=f"agent_os.approval.{decision}", entity_type="agent_approval",
        entity_id=a.id, seller_id=current_user.id, actor_user_id=current_user.id, actor_type="seller",
        after={"title": a.title},
    )
    await db.commit()
    return {"success": True, "status": a.status, "followup_sent": bool(followup_text)}


@router.post("/approvals/{approval_id}/approve")
async def approve(approval_id: int, current_user: User = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    return await _decide_approval(approval_id, "approved", current_user, db)


@router.post("/approvals/{approval_id}/reject")
async def reject(approval_id: int, current_user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    return await _decide_approval(approval_id, "rejected", current_user, db)


@router.get("/negotiations")
async def negotiations(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(NegotiationState).where(NegotiationState.seller_id == current_user.id)
        .order_by(desc(NegotiationState.id)).limit(30)
    )
    return [
        {
            "id": s.id, "conversation_id": s.conversation_id, "product_id": s.product_id,
            "list_price": s.list_price, "floor_price": s.floor_price, "current_offer": s.current_offer,
            "last_customer_ask": s.last_customer_ask, "rounds": s.rounds, "status": s.status,
            "history": s.history_json or [],
        }
        for s in r.scalars().all()
    ]

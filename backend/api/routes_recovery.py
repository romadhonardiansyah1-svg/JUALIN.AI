"""
P2.6 — Recovery API read-only (observe mode) + P4.1 approve/reject (approval mode).

GET /api/recovery/overview
GET /api/recovery/opportunities
GET /api/recovery/opportunities/{id}
POST /api/recovery/opportunities/{id}/approve
POST /api/recovery/opportunities/{id}/reject
"""
from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
import uuid
from pydantic import BaseModel

from models.database import get_db
from models.user import User
from api.routes_auth import get_current_user
from models.payment_recovery import RevenueOpportunity, PaymentAttempt
from models.order import Order

router = APIRouter()


class ApproveRequest(BaseModel):
    expected_version: int
    action_digest: str
    idempotency_key: str


class RejectRequest(BaseModel):
    expected_version: int
    idempotency_key: str
    reason: Optional[str] = None


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    # Mask: +62••••••1234
    if len(phone) <= 4:
        return "••••"
    return f"{phone[:3]}••••••{phone[-4:]}"


def _masked_reference(url: str | None) -> dict:
    """Return trusted domain + masked path, no raw token."""
    if not url:
        return {"trusted_domain": None, "masked_path": None}
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = parsed.hostname or "unknown"
        path = parsed.path or "/"
        # Mask path: /invoice/••••7K9
        if len(path) > 8:
            masked = f"{path[:9]}••••{path[-3:]}" if len(path) > 12 else "/••••"
        else:
            masked = "/••••"
        return {"trusted_domain": domain, "masked_path": masked}
    except Exception:
        return {"trusted_domain": "unknown", "masked_path": "/••••"}


@router.get("/overview")
async def get_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Counts per status for seller
    counts_q = await db.execute(
        select(RevenueOpportunity.status, func.count(RevenueOpportunity.id)).where(
            RevenueOpportunity.seller_id == current_user.id
        ).group_by(RevenueOpportunity.status)
    )
    counts_raw = dict(counts_q.all())

    # Map to expected keys
    counts = {
        "awaiting_approval": counts_raw.get("awaiting_approval", 0),
        "scheduled": counts_raw.get("scheduled", 0),
        "suppressed": counts_raw.get("suppressed", 0),
        "detected": counts_raw.get("detected", 0),
        "dispatched": counts_raw.get("dispatched", 0),
        "payment_observed": counts_raw.get("payment_observed", 0),
        "expired_unpaid": counts_raw.get("expired_unpaid", 0),
    }

    # Honest ledger aggregates (P5.1): observed-after-acceptance only.
    from models.payment_recovery import OutcomeEvent, AttributionAssessment

    observed_q = await db.execute(
        select(
            func.coalesce(func.sum(OutcomeEvent.amount), 0),
            func.count(OutcomeEvent.id),
        ).where(
            OutcomeEvent.seller_id == current_user.id,
            OutcomeEvent.event_type == "payment_observed",
        )
    )
    observed_row = observed_q.one()
    observed_amount = observed_row[0] or 0
    observed_orders = int(observed_row[1] or 0)

    attributed_q = await db.execute(
        select(
            func.coalesce(func.sum(AttributionAssessment.estimate), 0),
            func.count(AttributionAssessment.id),
        ).where(
            AttributionAssessment.seller_id == current_user.id,
            AttributionAssessment.method == "rule_attributed",
        )
    )
    attributed_row = attributed_q.one()
    attributed_amount = attributed_row[0] or 0
    attributed_orders = int(attributed_row[1] or 0)

    from datetime import datetime, timezone
    from config import get_settings
    from services.payment_recovery.outcomes import RULE_VERSION

    now = datetime.now(timezone.utc)
    settings = get_settings()
    mode = getattr(settings, "PAYMENT_RECOVERY_MODE", "observe") or "observe"
    if not getattr(settings, "ENABLE_PAYMENT_RECOVERY", False):
        mode = "observe"

    return JSONResponse(
        content={
            "as_of": now.isoformat(),
            "mode": mode,
            "counts": counts,
            "outcomes": {
                "observed_payment": {
                    "amount": str(observed_amount),
                    "currency": "IDR",
                    "orders": observed_orders,
                },
                "rule_attributed": {
                    "amount": str(attributed_amount),
                    "currency": "IDR",
                    "orders": attributed_orders,
                    "rule_version": RULE_VERSION,
                },
                "causal_estimate": None,
                "disclaimer": (
                    "Data ini menunjukkan urutan waktu, bukan bukti bahwa "
                    "pengingat menyebabkan pembayaran."
                ),
            },
            "stale": False,
        },
        headers={
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/opportunities")
async def list_opportunities(
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(RevenueOpportunity).where(RevenueOpportunity.seller_id == current_user.id)

    allowed_statuses = {"detected", "awaiting_approval", "dispatch_pending", "dispatched", "suppressed", "payment_observed", "expired_unpaid", "rejected", "expired"}
    if status:
        if status not in allowed_statuses:
            # Allowlist status, return empty if invalid
            return JSONResponse(content={"items": [], "total": 0, "limit": limit, "offset": offset})
        q = q.where(RevenueOpportunity.status == status)

    # Stable sort created_at DESC, id DESC
    q = q.order_by(RevenueOpportunity.created_at.desc(), RevenueOpportunity.id.desc()).limit(limit).offset(offset)

    result = await db.execute(q)
    items = result.scalars().all()

    # Get total count for pagination
    count_q = await db.execute(
        select(func.count(RevenueOpportunity.id)).where(RevenueOpportunity.seller_id == current_user.id)
    )
    total = count_q.scalar() or 0

    # Masked serialization
    serialized = []
    for opp in items:
        serialized.append(
            {
                "id": str(opp.id),
                "state_version": opp.state_version,
                "status": opp.status,
                "order_id": opp.order_id,
                "amount": str(opp.amount_snapshot),
                "currency": opp.currency,
                "eligible_at": opp.eligible_at.isoformat() if opp.eligible_at else None,
                "expires_at": opp.expires_at.isoformat() if opp.expires_at else None,
                "suppression_code": opp.suppression_code,
                "created_at": opp.created_at.isoformat() if opp.created_at else None,
            }
        )

    return JSONResponse(
        content={"items": serialized, "total": total, "limit": limit, "offset": offset},
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/opportunities/{opportunity_id}")
async def get_opportunity_detail(
    opportunity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = await db.execute(
        select(RevenueOpportunity).where(
            RevenueOpportunity.id == opportunity_id,
            RevenueOpportunity.seller_id == current_user.id,
        )
    )
    opp = q.scalar_one_or_none()
    if not opp:
        return JSONResponse(status_code=404, content={"error": "opportunity_not_found", "message": "Peluang tidak ditemukan"})

    # Load order for reference (masked)
    order_q = await db.execute(select(Order).where(Order.id == opp.order_id))
    order = order_q.scalar_one_or_none()

    # Load payment attempt for expiry
    attempt_q = await db.execute(select(PaymentAttempt).where(PaymentAttempt.id == opp.payment_attempt_id))
    attempt = attempt_q.scalar_one_or_none()

    # Load pending recovery approval for exact digest (read-only; no materialization).
    from models.agent_os import AgentApproval

    approval_q = await db.execute(
        select(AgentApproval).where(
            AgentApproval.opportunity_id == opp.id,
            AgentApproval.seller_id == current_user.id,
            AgentApproval.status == "pending",
        )
    )
    approval = approval_q.scalar_one_or_none()
    action_digest = approval.action_digest if approval and approval.action_digest else None
    template_code = "payment_reminder_v1"
    if approval and isinstance(approval.detail_json, dict):
        template_code = approval.detail_json.get("template_code") or template_code

    recipient_masked = "+62••••••••••"
    if order and order.customer_phone:
        recipient_masked = _mask_phone(order.customer_phone)

    preview = {
        "template_code": template_code,
        "template_provider_status": "local_registry",
        "text": (
            f"Halo, pesanan {order.id if order else opp.order_id} senilai "
            f"Rp{opp.amount_snapshot} masih menunggu pembayaran."
        ),
        "payment_reference": _masked_reference(order.payment_url if order else None),
        "scheduled_at": opp.eligible_at.isoformat() if opp.eligible_at else None,
        "action_digest": action_digest,
        "expires_at": (
            approval.expires_at.isoformat()
            if approval and getattr(approval, "expires_at", None)
            else (opp.expires_at.isoformat() if opp.expires_at else None)
        ),
    }

    return JSONResponse(
        content={
            "id": str(opp.id),
            "state_version": opp.state_version,
            "status": opp.status,
            "can_decide": bool(
                approval
                and opp.status == "awaiting_approval"
                and action_digest
            ),
            "approval": (
                {
                    "id": approval.id,
                    "status": approval.status,
                    "action_digest": action_digest,
                    "expires_at": preview["expires_at"],
                }
                if approval
                else None
            ),
            "order": {
                "reference": f"ORD-{opp.order_id}",
                "amount": str(opp.amount_snapshot),
                "currency": opp.currency,
                "payment_expires_at": attempt.payment_expires_at.isoformat() if attempt and attempt.payment_expires_at else None,
            },
            "recipient": {"masked": recipient_masked},
            "preview": preview,
            "evidence": opp.evidence_json or [],
        },
        headers={"Cache-Control": "private, no-store"},
    )


@router.post("/opportunities/{opportunity_id}/approve")
async def approve_opportunity(
    opportunity_id: uuid.UUID,
    body: ApproveRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    P4.1 — Approve exact recovery action atomically.
    Returns 202 accepted for processing, idempotent replay via idempotency_key.
    """
    # Check capability: must be in approval mode
    from config import get_settings

    settings = get_settings()
    if not settings.ENABLE_PAYMENT_RECOVERY or settings.PAYMENT_RECOVERY_MODE != "approval":
        return JSONResponse(
            status_code=403,
            content={"error": "capability_forbidden", "message": "Mode approval belum diaktifkan"},
        )

    # Owner only by default
    if current_user.role != "seller" and current_user.role != "admin":
        # Check explicit permission? For MVP, owner only
        pass

    try:
        from services.payment_recovery.approval import approve_recovery

        result = await approve_recovery(
            db,
            principal_seller_id=current_user.id,
            opportunity_id=opportunity_id,
            expected_version=body.expected_version,
            action_digest_from_client=body.action_digest,
            idempotency_key=body.idempotency_key,
            request_body=body.model_dump(),
        )
        return JSONResponse(status_code=202, content=result, headers={"Cache-Control": "private, no-store"})
    except HTTPException as he:
        # Return typed error contract
        raise he
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "internal_error", "message": str(e)})


@router.post("/opportunities/{opportunity_id}/reject")
async def reject_opportunity(
    opportunity_id: uuid.UUID,
    body: RejectRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    P4.1 — Reject pending recovery approval.
    """
    from config import get_settings

    settings = get_settings()
    if not settings.ENABLE_PAYMENT_RECOVERY or settings.PAYMENT_RECOVERY_MODE not in ("approval", "observe"):
        return JSONResponse(
            status_code=403,
            content={"error": "capability_forbidden", "message": "Mode tidak diizinkan"},
        )

    # Simple reject implementation: lock and transition
    from models.agent_os import AgentApproval

    # Lock approval FOR UPDATE
    approval_q = await db.execute(
        select(AgentApproval)
        .where(AgentApproval.opportunity_id == opportunity_id, AgentApproval.seller_id == current_user.id)
        .with_for_update()
    )
    approval = approval_q.scalars().first()
    if not approval:
        return JSONResponse(status_code=404, content={"error": "approval_not_found"})

    if approval.status != "pending":
        return JSONResponse(status_code=409, content={"error": "approval_stale"})

    # Load opportunity FOR UPDATE
    opp_q = await db.execute(
        select(RevenueOpportunity)
        .where(RevenueOpportunity.id == opportunity_id, RevenueOpportunity.seller_id == current_user.id)
        .with_for_update()
    )
    opp = opp_q.scalar_one_or_none()
    if not opp:
        return JSONResponse(status_code=404, content={"error": "opportunity_not_found"})

    if opp.state_version != body.expected_version:
        return JSONResponse(status_code=409, content={"error": "approval_stale", "current_version": opp.state_version})

    # Idempotency check for reject
    from services.payment_recovery.approval import find_decision_receipt, hash_decision_request

    request_hash = hash_decision_request(body.model_dump())
    replay = await find_decision_receipt(
        db,
        seller_id=current_user.id,
        decision_scope="recovery.reject",
        opportunity_id=opportunity_id,
        idempotency_key=body.idempotency_key,
    )
    if replay:
        if replay.decision_request_hash == request_hash:
            return JSONResponse(content=replay.decision_response_json or {"status": "rejected"})
        else:
            return JSONResponse(status_code=409, content={"error": "idempotency_conflict"})

    # Bind intent
    approval.decision_scope = "recovery.reject"
    approval.decision_idempotency_key = body.idempotency_key
    approval.decision_request_hash = request_hash
    await db.flush()

    # Transition
    from datetime import datetime, timezone

    approval.status = "rejected"
    approval.reason = body.reason or "rejected by seller"
    opp.status = "rejected"
    opp.state_version += 1
    opp.updated_at = datetime.now(timezone.utc)

    response_snapshot = {
        "approval": {"id": approval.id, "status": "rejected"},
        "opportunity": {"id": str(opp.id), "status": opp.status, "state_version": opp.state_version},
        "message": "Peluang ditolak",
    }
    approval.decision_response_json = response_snapshot
    await db.commit()

    return JSONResponse(content=response_snapshot, headers={"Cache-Control": "private, no-store"})

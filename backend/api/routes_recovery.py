"""
P2.6 — Recovery API read-only (observe mode).

GET /api/recovery/overview
GET /api/recovery/opportunities
GET /api/recovery/opportunities/{id}

Read-only, masked fields, pagination, tenant 404, money strings, no approve route in Phase 2.
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
import uuid

from models.database import get_db
from models.user import User
from api.routes_auth import get_current_user
from models.payment_recovery import RevenueOpportunity, PaymentAttempt
from models.order import Order

router = APIRouter()


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

    # Outcomes observed (sum of amount_snapshot for payment_observed)
    observed_q = await db.execute(
        select(func.coalesce(func.sum(RevenueOpportunity.amount_snapshot), 0)).where(
            RevenueOpportunity.seller_id == current_user.id,
            RevenueOpportunity.status == "payment_observed",
        )
    )
    observed_amount = observed_q.scalar() or 0

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    return JSONResponse(
        content={
            "as_of": now.isoformat(),
            "mode": "observe",  # Phase 2 only observe
            "counts": counts,
            "outcomes": {
                "observed_payment": {"amount": str(observed_amount), "currency": "IDR", "orders": counts.get("payment_observed", 0)},
                "rule_attributed": {"amount": "0.00", "currency": "IDR", "orders": 0},
                "causal_estimate": None,
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

    # Build masked response
    recipient_masked = "+62••••••1234"  # Placeholder, real would come from ContactSubject via HMAC
    # For observe, we don't have contact subject yet? We have permission, but we mask
    preview = {
        "template_code": "payment_reminder_v1",
        "text": f"Halo, pesanan {order.id if order else opp.order_id} di toko Anda senilai Rp{opp.amount_snapshot} masih menunggu pembayaran.",
        "payment_reference": _masked_reference(order.payment_url if order else None),
        "scheduled_at": opp.eligible_at.isoformat() if opp.eligible_at else None,
        "action_digest": "pending_approval_required_in_next_phase",
        "expires_at": opp.expires_at.isoformat() if opp.expires_at else None,
    }

    return JSONResponse(
        content={
            "id": str(opp.id),
            "state_version": opp.state_version,
            "status": opp.status,
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

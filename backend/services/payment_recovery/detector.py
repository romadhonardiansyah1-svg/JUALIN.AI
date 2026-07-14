"""
P2.6 — Deterministic detector in observe mode.

Atomic opportunity creation via signal_key, evidence only, no PII.
No AgentApproval creation in Phase 2 (P4.0 owner).
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.order import Order, OrderStatus
from models.payment_recovery import PaymentAttempt, RevenueOpportunity, ContactPermission
from services.payment_recovery.provider_capabilities import (
    evaluate_payment_provider,
    is_trusted_https_link,
)
from services.payment_recovery.policy import parse_legacy_expiry


GRACE_PERIOD_MINUTES = 60  # 1 hour grace to avoid interrupting fresh payment page


def build_signal_key(seller_id: int, order_id: int, payment_attempt_id: uuid.UUID) -> str:
    return f"payment-opportunity:v1:{seller_id}:{order_id}:{payment_attempt_id}"


async def detect_payment_recovery_opportunities(
    db: AsyncSession,
    *,
    seller_id: int | None = None,
    now: datetime | None = None,
) -> list[RevenueOpportunity]:
    """
    Detect pending payment recovery opportunities in observe mode.
    Returns list of created or existing opportunities that are eligible.
    - seller-scoped
    - grace period elapsed
    - immutable current payment cycle
    - no existing signal/opportunity
    - parseable expiry and trusted link
    - active explicit permission
    - provider capability
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=GRACE_PERIOD_MINUTES)

    # Base query: pending orders with created_at < cutoff
    order_q = select(Order).where(
        Order.status == OrderStatus.PENDING,
        Order.created_at < cutoff,
    )
    if seller_id:
        order_q = order_q.where(Order.seller_id == seller_id)

    order_result = await db.execute(order_q)
    orders = order_result.scalars().all()

    created_opps = []

    for order in orders:
        # Get current payment attempt
        attempt_q = await db.execute(
            select(PaymentAttempt).where(
                PaymentAttempt.order_id == order.id,
                PaymentAttempt.seller_id == order.seller_id,
                PaymentAttempt.is_current == True,
            )
        )
        attempt = attempt_q.scalar_one_or_none()
        if not attempt:
            continue

        # Check attempt expiry parseable
        expiry = attempt.payment_expires_at
        if not expiry:
            # Try legacy order.payment_expires_at string
            expiry = parse_legacy_expiry(order.payment_expires_at)
        if not expiry:
            # payment_expiry_unknown -> observe suppressed evidence only if useful
            # For MVP, skip creation, but could log evidence
            continue

        if expiry <= now:
            # Already expired
            continue

        # Check trusted link
        # Prefer attempt trusted_link_reference? For now use order.payment_url
        payment_url = order.payment_url or ""
        # If trusted_link_reference exists, consider it as trusted? For MVP, check payment_url
        if not is_trusted_https_link(payment_url):
            # Check if attempt has trusted_link_reference that is https?
            # For MVP, if not trusted, suppress (no opportunity)
            continue

        # Check provider capabilities
        prov_caps = evaluate_payment_provider(
            provider=attempt.provider,
            payment_url=payment_url,
            payment_qr_data=order.payment_qr_data,
            payment_expires_at_str=order.payment_expires_at,
            invoice_id=attempt.external_attempt_id or order.payment_invoice_id,
        )
        if not prov_caps.trusted_https_link or not prov_caps.exact_expiry or not prov_caps.stable_cycle_id:
            continue

        # Check active explicit permission for exact order/payment cycle
        # Need contact_subject_id? For MVP, we check any active permission for this order/attempt
        perm_q = await db.execute(
            select(ContactPermission).where(
                ContactPermission.seller_id == order.seller_id,
                ContactPermission.order_id == order.id,
                ContactPermission.payment_attempt_id == attempt.id,
                ContactPermission.status == "active",
                ContactPermission.purpose == "transactional_payment_reminder",
            )
        )
        perm = perm_q.scalar_one_or_none()
        if not perm:
            # No active consent -> no opportunity in observe mode (could create suppressed evidence)
            continue

        # Check existing opportunity via signal_key
        signal_key = build_signal_key(order.seller_id, order.id, attempt.id)
        existing_q = await db.execute(
            select(RevenueOpportunity).where(RevenueOpportunity.signal_key == signal_key)
        )
        existing = existing_q.scalar_one_or_none()
        if existing:
            created_opps.append(existing)
            continue

        # Build evidence (no PII, only codes and timestamps)
        evidence = [
            {"code": "payment_pending", "observed_at": now.isoformat()},
            {"code": "payment_expiry_valid", "observed_at": now.isoformat(), "expiry": expiry.isoformat()},
            {"code": "trusted_link", "observed_at": now.isoformat()},
            {"code": "consent_active", "observed_at": now.isoformat(), "permission_id": str(perm.id)},
            {"code": "provider_capability_ok", "observed_at": now.isoformat(), "provider": attempt.provider},
        ]

        # Atomic creation via INSERT ON CONFLICT DO NOTHING
        insert_sql = text(
            """
            INSERT INTO revenue_opportunities (
                id, seller_id, order_id, payment_attempt_id, opportunity_type, status,
                signal_key, amount_snapshot, currency, evidence_json, policy_version,
                state_version, eligible_at, expires_at, created_at, updated_at
            ) VALUES (
                :id, :seller_id, :order_id, :payment_attempt_id, 'pending_payment_recovery', 'detected',
                :signal_key, :amount_snapshot, :currency, CAST(:evidence AS JSON), 1,
                1, :eligible_at, :expires_at, now(), now()
            )
            ON CONFLICT (signal_key) DO NOTHING
            RETURNING id
            """
        )
        new_id = uuid.uuid4()
        result = await db.execute(
            insert_sql,
            {
                "id": new_id,
                "seller_id": order.seller_id,
                "order_id": order.id,
                "payment_attempt_id": attempt.id,
                "signal_key": signal_key,
                "amount_snapshot": str(attempt.amount),
                "currency": attempt.currency,
                "evidence": __import__("json").dumps(evidence),
                "eligible_at": now,
                "expires_at": expiry,
            },
        )
        returned = result.fetchone()
        if returned is None:
            # Conflict — fetch existing
            existing_q = await db.execute(
                select(RevenueOpportunity).where(RevenueOpportunity.signal_key == signal_key)
            )
            existing = existing_q.scalar_one()
            created_opps.append(existing)
        else:
            # Fetch newly created
            new_q = await db.execute(select(RevenueOpportunity).where(RevenueOpportunity.id == returned[0]))
            new_opp = new_q.scalar_one()
            created_opps.append(new_opp)

    await db.commit()
    return created_opps


async def get_opportunity_for_seller(
    db: AsyncSession,
    seller_id: int,
    opportunity_id: uuid.UUID,
) -> RevenueOpportunity | None:
    """Tenant-scoped read-only lookup."""
    q = await db.execute(
        select(RevenueOpportunity).where(
            RevenueOpportunity.id == opportunity_id,
            RevenueOpportunity.seller_id == seller_id,
        )
    )
    return q.scalar_one_or_none()

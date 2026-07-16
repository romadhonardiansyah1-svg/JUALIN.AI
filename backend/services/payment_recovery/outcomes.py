"""
P5.1 — Honest append-only recovery outcome ledger.

Observed payment ≠ causal recovery. Rule-attributed requires provider acceptance
before payment inside a documented window. Causal remains null without holdout.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging_config import get_logger
from models.payment_recovery import (
    AttributionAssessment,
    OutcomeEvent,
    OutboundDispatch,
    RevenueOpportunity,
)

logger = get_logger(__name__)

RULE_VERSION = "recovery_attribution_v1"
ATTRIBUTION_WINDOW = timedelta(hours=72)


def _as_decimal(value: object) -> Decimal | None:
    try:
        if isinstance(value, Decimal):
            amount = value
        else:
            amount = Decimal(str(value))
        if amount < 0:
            return None
        return amount.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _get_existing_outcome(
    db: AsyncSession,
    *,
    source_event_key: str,
) -> OutcomeEvent | None:
    q = await db.execute(
        select(OutcomeEvent).where(OutcomeEvent.source_event_key == source_event_key)
    )
    return q.scalar_one_or_none()


async def record_verified_payment_outcome(
    db: AsyncSession,
    *,
    seller_id: int,
    order_id: int,
    payment_attempt_id: uuid.UUID,
    opportunity: RevenueOpportunity,
    dispatch: OutboundDispatch | None,
    amount: object,
    currency: str = "IDR",
    observed_at: datetime,
    source_event_key: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Insert OutcomeEvent once for a verified payment fact and optionally attribute.

    Payment before provider acceptance is stored as a payment fact only when a
    dispatch acceptance exists later can attribution be created; pre-acceptance
    payments do not enter observed-after-reminder aggregates.
    """
    amount_dec = _as_decimal(amount)
    if amount_dec is None:
        return {"applied": False, "reason": "invalid_amount"}
    if opportunity.seller_id != seller_id or opportunity.order_id != order_id:
        return {"applied": False, "reason": "tenant_or_order_mismatch"}
    if opportunity.payment_attempt_id != payment_attempt_id:
        return {"applied": False, "reason": "wrong_payment_cycle"}

    existing = await _get_existing_outcome(db, source_event_key=source_event_key)
    if existing:
        return {
            "applied": False,
            "reason": "duplicate_source_event",
            "outcome_event_id": str(existing.id),
        }

    observed_at = _aware(observed_at) or datetime.now(timezone.utc)
    accepted_at = _aware(dispatch.accepted_at) if dispatch else None
    after_acceptance = bool(
        dispatch
        and dispatch.status == "accepted"
        and accepted_at is not None
        and observed_at > accepted_at
    )

    # Payment before acceptance is a durable payment fact but not
    # observed-after-reminder for this opportunity cycle.
    event_type = "payment_observed" if after_acceptance else "payment_verified_pre_acceptance"

    outcome = OutcomeEvent(
        seller_id=seller_id,
        order_id=order_id,
        payment_attempt_id=payment_attempt_id,
        opportunity_id=opportunity.id,
        dispatch_id=dispatch.id if dispatch else None,
        event_type=event_type,
        source_event_key=source_event_key,
        amount=amount_dec,
        currency=(currency or "IDR")[:3].upper(),
        observed_at=observed_at,
        evidence_json={
            "after_acceptance": after_acceptance,
            "dispatch_status": getattr(dispatch, "status", None),
            **(evidence or {}),
        },
    )
    db.add(outcome)
    await db.flush()

    transitions = [f"outcome:{event_type}"]

    if after_acceptance and opportunity.status == "dispatched":
        opportunity.status = "payment_observed"
        opportunity.state_version = int(opportunity.state_version or 0) + 1
        transitions.append("opportunity:dispatched->payment_observed")

    assessment = None
    if after_acceptance and accepted_at is not None:
        window_end = accepted_at + ATTRIBUTION_WINDOW
        # Cap by opportunity/payment expiry if present on evidence only; MVP uses 72h.
        if observed_at <= window_end:
            assessment = AttributionAssessment(
                seller_id=seller_id,
                outcome_event_id=outcome.id,
                method="rule_attributed",
                rule_version=RULE_VERSION,
                window_start=accepted_at,
                window_end=window_end,
                estimate=amount_dec,
                confidence="rule_only_not_causal",
                evidence_json={
                    "disclaimer": "temporal correlation under documented rule; not causal lift",
                },
            )
            db.add(assessment)
            transitions.append("attribution:rule_attributed")

    await db.flush()
    logger.info(
        "Recorded recovery outcome event",
        extra={
            "seller_id": seller_id,
            "order_id": order_id,
            "event_type": event_type,
            "after_acceptance": after_acceptance,
            "has_attribution": assessment is not None,
        },
    )
    return {
        "applied": True,
        "reason": "recorded",
        "outcome_event_id": str(outcome.id),
        "event_type": event_type,
        "after_acceptance": after_acceptance,
        "attributed": assessment is not None,
        "transitions": transitions,
        "causal_estimate": None,
    }


async def reconcile_payment_for_opportunity(
    db: AsyncSession,
    *,
    seller_id: int,
    opportunity_id: uuid.UUID,
    amount: object,
    observed_at: datetime,
    source_event_key: str,
    currency: str = "IDR",
) -> dict[str, Any]:
    """
    Load seller-scoped opportunity + accepted dispatch (if any) and record outcome.
    """
    opp_q = await db.execute(
        select(RevenueOpportunity).where(
            RevenueOpportunity.id == opportunity_id,
            RevenueOpportunity.seller_id == seller_id,
        )
    )
    opportunity = opp_q.scalar_one_or_none()
    if not opportunity:
        return {"applied": False, "reason": "opportunity_not_found"}

    dispatch_q = await db.execute(
        select(OutboundDispatch).where(
            OutboundDispatch.opportunity_id == opportunity.id,
            OutboundDispatch.seller_id == seller_id,
        )
    )
    dispatch = dispatch_q.scalar_one_or_none()

    return await record_verified_payment_outcome(
        db,
        seller_id=seller_id,
        order_id=opportunity.order_id,
        payment_attempt_id=opportunity.payment_attempt_id,
        opportunity=opportunity,
        dispatch=dispatch,
        amount=amount,
        currency=currency,
        observed_at=observed_at,
        source_event_key=source_event_key,
    )


async def mark_expired_unpaid_if_due(
    db: AsyncSession,
    *,
    seller_id: int,
    opportunity_id: uuid.UUID,
    payment_expires_at: datetime | None,
    provider_state_known: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Bounded unpaid sweeper: only dispatched → expired_unpaid when expiry trusted
    and provider current state is known (not unknown).
    """
    now = _aware(now) or datetime.now(timezone.utc)
    expires = _aware(payment_expires_at)
    if not provider_state_known:
        return {"applied": False, "reason": "provider_state_unknown"}
    if not expires or expires > now:
        return {"applied": False, "reason": "not_expired"}

    opp_q = await db.execute(
        select(RevenueOpportunity).where(
            RevenueOpportunity.id == opportunity_id,
            RevenueOpportunity.seller_id == seller_id,
        )
    )
    opportunity = opp_q.scalar_one_or_none()
    if not opportunity:
        return {"applied": False, "reason": "opportunity_not_found"}
    if opportunity.status != "dispatched":
        return {"applied": False, "reason": "not_dispatched"}

    opportunity.status = "expired_unpaid"
    opportunity.terminal_reason_code = "payment_expired_unpaid"
    opportunity.state_version = int(opportunity.state_version or 0) + 1
    await db.flush()
    return {
        "applied": True,
        "reason": "expired_unpaid",
        "transitions": ["opportunity:dispatched->expired_unpaid"],
    }

"""
P4.3 — Transactional reminder opt-out (STOP / BERHENTI).

Exact keyword allowlist only. Ambiguous words like BATAL never auto-withdraw.
Recipient-level suppression beats order-scoped grants. Pre-network
opportunity/dispatch rows are suppressed; accepted stays a durable fact.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging_config import get_logger
from models.payment_recovery import (
    ContactPermission,
    ContactSubjectFingerprint,
    ContactSuppression,
    OutboundDispatch,
    RevenueOpportunity,
)
from services.contact_identity import hmac_fingerprint
from services.payment_consent import withdraw_consent
from services.payment_recovery.phone import normalize_indonesian_phone

logger = get_logger(__name__)

# Exact allowlist after trim + casefold. Provider-required aliases can be added
# only after explicit review of Meta templates/policy.
_STOP_KEYWORDS = frozenset({"stop", "berhenti"})

_PRE_NETWORK_DISPATCH = frozenset({"pending", "scheduled", "claimed", "revalidated"})
_PRE_NETWORK_OPPORTUNITY = frozenset(
    {"detected", "awaiting_approval", "dispatch_pending"}
)


def is_transactional_stop_keyword(text: str | None) -> bool:
    """Return True only for exact allowlisted STOP/BERHENTI tokens."""
    if not isinstance(text, str):
        return False
    token = text.strip().casefold()
    if not token:
        return False
    # Single-token exact match only — multi-word free text is not opt-out.
    if " " in token or "\n" in token or "\t" in token:
        return False
    return token in _STOP_KEYWORDS


async def _resolve_subject_id(
    db: AsyncSession,
    *,
    seller_id: int,
    channel: str,
    phone: str,
) -> tuple[uuid.UUID | None, str | None]:
    norm = normalize_indonesian_phone(phone)
    if norm.status != "valid" or not norm.e164:
        return None, None
    fingerprint, _ = hmac_fingerprint(norm.e164)
    fp_q = await db.execute(
        select(ContactSubjectFingerprint).where(
            ContactSubjectFingerprint.seller_id == seller_id,
            ContactSubjectFingerprint.channel == channel,
            ContactSubjectFingerprint.fingerprint == fingerprint,
            ContactSubjectFingerprint.retired_at.is_(None),
        )
    )
    fp = fp_q.scalar_one_or_none()
    if not fp:
        return None, fingerprint
    return fp.contact_subject_id, fingerprint


async def apply_transactional_stop(
    db: AsyncSession,
    *,
    seller_id: int,
    channel: str,
    sender_phone: str,
    source_event: str | None = None,
) -> dict[str, Any]:
    """
    Apply STOP for one seller + channel + sender.

    - creates/keeps active ContactSuppression
    - withdraws active transactional reminder permissions
    - cancels pre-network dispatches for the subject
    - suppresses pre-network opportunities for those dispatches and withdrawn orders
    - leaves request_in_flight / provider_unknown / accepted alone (no resend path)
    """
    subject_id, fingerprint = await _resolve_subject_id(
        db,
        seller_id=seller_id,
        channel=channel,
        phone=sender_phone,
    )
    if subject_id is None:
        logger.info(
            "STOP ignored: contact subject not resolved for seller/channel",
            extra={"seller_id": seller_id, "channel": channel},
        )
        return {
            "applied": False,
            "reason": "contact_subject_not_found",
            "seller_id": seller_id,
        }

    now = datetime.now(timezone.utc)
    transitions: list[str] = []

    supp_q = await db.execute(
        select(ContactSuppression).where(
            ContactSuppression.seller_id == seller_id,
            ContactSuppression.contact_subject_id == subject_id,
            ContactSuppression.channel == channel,
            ContactSuppression.purpose == "transactional_payment_reminder",
            ContactSuppression.status == "active",
        )
    )
    suppression = supp_q.scalar_one_or_none()
    if not suppression:
        if not fingerprint:
            fingerprint, _ = hmac_fingerprint(
                normalize_indonesian_phone(sender_phone).e164 or sender_phone
            )
        suppression = ContactSuppression(
            seller_id=seller_id,
            channel=channel,
            contact_subject_id=subject_id,
            address_fingerprint=fingerprint,
            fingerprint_key_version=1,
            purpose="transactional_payment_reminder",
            status="active",
            source_event=(source_event or "inbound_stop")[:255],
        )
        db.add(suppression)
        transitions.append("suppression:created")
    else:
        transitions.append("suppression:already_active")

    # Order ids remain available on permission rows after withdraw for scoping.
    order_q = await db.execute(
        select(ContactPermission.order_id).where(
            ContactPermission.seller_id == seller_id,
            ContactPermission.contact_subject_id == subject_id,
            ContactPermission.channel == channel,
            ContactPermission.purpose == "transactional_payment_reminder",
            ContactPermission.order_id.is_not(None),
        )
    )
    order_ids = {row[0] for row in order_q.all() if row[0] is not None}

    withdrawn = await withdraw_consent(
        db,
        seller_id=seller_id,
        contact_subject_id=subject_id,
        channel=channel,
        purpose="transactional_payment_reminder",
    )
    if withdrawn:
        transitions.append(f"permissions:withdrawn:{withdrawn}")

    dispatch_q = await db.execute(
        select(OutboundDispatch).where(
            OutboundDispatch.seller_id == seller_id,
            OutboundDispatch.contact_subject_id == subject_id,
        )
    )
    dispatches = list(dispatch_q.scalars().all())
    cancelled_dispatch_opp_ids: set[uuid.UUID] = set()
    for dispatch in dispatches:
        if dispatch.status in _PRE_NETWORK_DISPATCH:
            previous = dispatch.status
            dispatch.status = "cancelled"
            dispatch.last_error_code = "consent_withdrawn"
            cancelled_dispatch_opp_ids.add(dispatch.opportunity_id)
            transitions.append(f"dispatch:{previous}->cancelled")
        # request_in_flight / provider_unknown / accepted: no resend, no cancel

    if cancelled_dispatch_opp_ids or order_ids:
        opp_filters = [
            RevenueOpportunity.seller_id == seller_id,
            RevenueOpportunity.status.in_(tuple(_PRE_NETWORK_OPPORTUNITY)),
        ]
        opp_q = await db.execute(select(RevenueOpportunity).where(*opp_filters))
        for opp in opp_q.scalars().all():
            match = opp.id in cancelled_dispatch_opp_ids or (
                opp.order_id in order_ids if order_ids else False
            )
            if not match:
                continue
            if opp.status not in _PRE_NETWORK_OPPORTUNITY:
                continue
            previous = opp.status
            opp.status = "suppressed"
            opp.suppression_code = "consent_withdrawn"
            opp.terminal_reason_code = "consent_withdrawn"
            opp.state_version = int(opp.state_version or 0) + 1
            transitions.append(f"opportunity:{previous}->suppressed")

    await db.flush()
    logger.info(
        "Transactional STOP applied",
        extra={
            "seller_id": seller_id,
            "channel": channel,
            "withdrawn_permissions": withdrawn,
            "transition_count": len(transitions),
        },
    )
    return {
        "applied": True,
        "reason": "stop_applied",
        "seller_id": seller_id,
        "contact_subject_id": str(subject_id),
        "withdrawn_permissions": withdrawn,
        "transitions": transitions,
    }

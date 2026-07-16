"""
P4.2a — Project durable WhatsApp delivery facts onto recovery domain.

Inbox persistence (P1.3) remains the source of truth for signed, deduplicated
normalized facts. This module is the single owner that may mutate
OutboundDispatch / RevenueOpportunity from those facts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging_config import get_logger
from models.inbox import Channel
from models.payment_recovery import OutboundDispatch, RevenueOpportunity

logger = get_logger(__name__)

# Submission statuses that may be promoted to accepted when a verified
# delivered/read fact arrives before (or without) send-finalize.
_ACCEPTANCE_FROM = frozenset({"request_in_flight", "provider_unknown"})

# Delivery rank is monotonic for positive outcomes. "failed" never downgrades
# a higher positive delivery fact and never implies submission rejection.
_DELIVERY_RANK = {
    "not_available": 0,
    "sent": 1,
    "delivered": 2,
    "read": 3,
}

_ALLOWED_STATUS = frozenset({"sent", "delivered", "read", "failed"})


def _parse_provider_timestamp(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (OverflowError, OSError, ValueError, TypeError):
        return None
    return None


def delivery_rank(status: str | None) -> int:
    if not status:
        return 0
    return _DELIVERY_RANK.get(status, 0)


def should_advance_delivery(current: str | None, incoming: str) -> bool:
    """Positive delivery facts advance; failed never downgrades delivered/read."""
    if incoming not in _ALLOWED_STATUS:
        return False
    if incoming == "failed":
        return delivery_rank(current) < delivery_rank("delivered")
    return delivery_rank(incoming) > delivery_rank(current)


async def project_whatsapp_delivery_fact(
    db: AsyncSession,
    *,
    fact: dict[str, Any],
) -> dict[str, Any]:
    """
    Apply one normalized delivery fact to at most one tenant-scoped dispatch.

    Returns a small sanitized result for webhook processing / tests. Never logs
    raw phone, token, or full payload.
    """
    provider = str(fact.get("provider") or "whatsapp_cloud")
    provider_account_id = str(fact.get("provider_account_id") or "").strip()
    message_id = str(fact.get("message_id") or "").strip()
    status = str(fact.get("status") or "").strip().lower()
    ts = _parse_provider_timestamp(fact.get("timestamp"))

    if not provider_account_id or not message_id or status not in _ALLOWED_STATUS:
        return {
            "applied": False,
            "reason": "invalid_delivery_fact",
            "transitions": [],
        }

    channel_q = await db.execute(
        select(Channel).where(
            Channel.type == "whatsapp",
            Channel.provider == provider,
            Channel.external_id == provider_account_id,
            Channel.status == "active",
        )
    )
    channel = channel_q.scalar_one_or_none()
    if not channel:
        logger.info(
            "Delivery fact ignored: no active channel for provider account",
            extra={"provider": provider},
        )
        return {
            "applied": False,
            "reason": "channel_not_found",
            "transitions": [],
        }

    dispatch_q = await db.execute(
        select(OutboundDispatch).where(
            OutboundDispatch.seller_id == channel.seller_id,
            OutboundDispatch.provider == provider,
            OutboundDispatch.channel_id == channel.id,
            OutboundDispatch.provider_message_id == message_id,
        )
    )
    dispatch = dispatch_q.scalar_one_or_none()
    if not dispatch:
        # Do not guess across tenants/channels when message id is unknown.
        logger.info(
            "Delivery fact stored without recovery domain mapping",
            extra={
                "provider": provider,
                "seller_id": channel.seller_id,
                "channel_id": channel.id,
            },
        )
        return {
            "applied": False,
            "reason": "dispatch_not_found",
            "seller_id": channel.seller_id,
            "channel_id": channel.id,
            "transitions": [],
        }

    transitions: list[str] = []
    now = datetime.now(timezone.utc)

    # 1) Acceptance promotion from verified delivered/read while submission
    #    is still ambiguous (request_in_flight / provider_unknown).
    if status in {"delivered", "read"} and dispatch.status in _ACCEPTANCE_FROM:
        previous_status = dispatch.status
        dispatch.status = "accepted"
        if dispatch.accepted_at is None:
            dispatch.accepted_at = ts or now
        transitions.append(f"submission:{previous_status}->accepted")

        opp_q = await db.execute(
            select(RevenueOpportunity).where(
                RevenueOpportunity.id == dispatch.opportunity_id,
                RevenueOpportunity.seller_id == dispatch.seller_id,
            )
        )
        opportunity = opp_q.scalar_one_or_none()
        if opportunity is not None and opportunity.status == "dispatch_pending":
            opportunity.status = "dispatched"
            opportunity.state_version = int(opportunity.state_version or 0) + 1
            transitions.append("opportunity:dispatch_pending->dispatched")

    # 2) Monotonic delivery_status facts. Failed never proves submission
    #    rejection and never triggers resend.
    if should_advance_delivery(dispatch.delivery_status, status):
        previous_delivery = dispatch.delivery_status or "not_available"
        if status == "failed":
            dispatch.delivery_status = "failed"
            if dispatch.delivery_failed_at is None:
                dispatch.delivery_failed_at = ts or now
        else:
            dispatch.delivery_status = status
            if status == "delivered" and dispatch.delivered_at is None:
                dispatch.delivered_at = ts or now
            if status == "read":
                if dispatch.delivered_at is None:
                    dispatch.delivered_at = ts or now
                if dispatch.read_at is None:
                    dispatch.read_at = ts or now
        transitions.append(f"delivery:{previous_delivery}->{dispatch.delivery_status}")

    applied = bool(transitions)
    if applied:
        logger.info(
            "Projected delivery fact onto recovery dispatch",
            extra={
                "seller_id": dispatch.seller_id,
                "dispatch_id": str(dispatch.id),
                "status": status,
                "transition_count": len(transitions),
            },
        )

    return {
        "applied": applied,
        "reason": "projected" if applied else "no_transition",
        "seller_id": dispatch.seller_id,
        "dispatch_id": str(dispatch.id),
        "transitions": transitions,
    }

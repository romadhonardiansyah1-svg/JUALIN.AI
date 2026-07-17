"""
P4.0 — Materialize current pending approval (observe -> approval transition).

- Lock seller-scoped opportunity and current facts
- If terminal or not eligible -> suppress/expire
- If eligible, build canonical action + action_revision and create awaiting_approval + pending AgentApproval in same transaction
- Partial unique ensures one pending per opportunity
- GET/list/detail remain read-only
"""
from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.agent_os import AgentApproval
from models.inbox import Channel
from models.order import Order
from models.payment_recovery import ContactPermission, PaymentAttempt, RevenueOpportunity
from models.wa_template import WhatsAppMessageTemplate
from services.payment_recovery.actions import (
    action_digest,
    build_canonical_action,
    canonical_scalar,
)

settings = get_settings()


def _keyed_fingerprint(value: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _provider_template_content_digest(template: WhatsAppMessageTemplate) -> str:
    return action_digest(
        {
            "name": template.name,
            "language": template.language or "id",
            "body": template.body or "",
            "variables": template.variables_json or [],
            "provider_template_id": template.provider_template_id or "",
        }
    )


def build_bound_recovery_action(
    *,
    opportunity: RevenueOpportunity,
    order: Order,
    attempt: PaymentAttempt,
    permission: ContactPermission,
    channel: Channel,
    template: WhatsAppMessageTemplate,
    scheduled_at,
    policy_version: int,
) -> tuple[dict, dict]:
    """Build the JSON-safe action and exact provider parameters from current facts."""
    template_params = canonical_scalar({
        "language": template.language or "id",
        "body": [str(order.id), format(Decimal(str(attempt.amount)), "f")],
    })
    payment_reference = (
        attempt.trusted_link_reference
        or attempt.external_attempt_id
        or str(attempt.id)
    )
    raw_action = build_canonical_action(
        action_version=1,
        action_type="payment_recovery",
        purpose="transactional_payment_reminder",
        seller_id=opportunity.seller_id,
        opportunity_id=str(opportunity.id),
        order_id=order.id,
        payment_attempt_id=str(attempt.id),
        amount=Decimal(str(opportunity.amount_snapshot)),
        currency=opportunity.currency,
        payment_expires_at_utc=attempt.payment_expires_at,
        action_revision=1,
        contact_subject_id=str(permission.contact_subject_id),
        contact_permission_id=str(permission.id),
        recipient_fingerprint=permission.address_fingerprint,
        channel_id=channel.id,
        channel_type=channel.type,
        provider_account_fingerprint=_keyed_fingerprint(channel.external_id or str(channel.id)),
        provider_template_name=template.name,
        provider_template_locale=template.language or "id",
        provider_template_content_digest=_provider_template_content_digest(template),
        provider_template_version=str(template.provider_template_id or template.id),
        template_params_digest=action_digest(template_params),
        payment_reference_fingerprint=_keyed_fingerprint(payment_reference),
        payment_reference_fingerprint_key_version=1,
        scheduled_at_utc=scheduled_at,
        policy_version=policy_version,
    )
    return canonical_scalar(raw_action), template_params


async def materialize_approval_for_opportunity(
    db: AsyncSession,
    *,
    seller_id: int,
    opportunity_id: uuid.UUID,
    policy_version: int = 1,
) -> AgentApproval | None:
    """Create one seller-bound pending approval from current production facts."""
    opp_q = await db.execute(
        select(RevenueOpportunity)
        .where(
            RevenueOpportunity.id == opportunity_id,
            RevenueOpportunity.seller_id == seller_id,
        )
        .with_for_update()
    )
    opp = opp_q.scalar_one_or_none()
    if not opp or opp.status not in ("detected", "awaiting_approval"):
        return None

    existing_q = await db.execute(
        select(AgentApproval).where(
            AgentApproval.opportunity_id == opportunity_id,
            AgentApproval.seller_id == seller_id,
            AgentApproval.status == "pending",
        )
    )
    existing = existing_q.scalar_one_or_none()
    if existing:
        return existing

    order_q = await db.execute(
        select(Order).where(Order.id == opp.order_id, Order.seller_id == seller_id)
    )
    order = order_q.scalar_one_or_none()
    if not order:
        return None

    attempt_q = await db.execute(
        select(PaymentAttempt).where(
            PaymentAttempt.id == opp.payment_attempt_id,
            PaymentAttempt.order_id == order.id,
            PaymentAttempt.seller_id == seller_id,
            PaymentAttempt.is_current.is_(True),
        )
    )
    attempt = attempt_q.scalar_one_or_none()
    if not attempt:
        return None

    now = datetime.now(timezone.utc)
    perm_q = await db.execute(
        select(ContactPermission).where(
            ContactPermission.seller_id == seller_id,
            ContactPermission.order_id == order.id,
            ContactPermission.payment_attempt_id == attempt.id,
            ContactPermission.channel == "whatsapp",
            ContactPermission.purpose == "transactional_payment_reminder",
            ContactPermission.scope_type == "order_payment_cycle",
            ContactPermission.status == "active",
            or_(ContactPermission.expires_at.is_(None), ContactPermission.expires_at > now),
        )
    )
    permission = perm_q.scalar_one_or_none()
    if not permission:
        return None

    channel_q = await db.execute(
        select(Channel)
        .where(
            Channel.seller_id == seller_id,
            Channel.type == permission.channel,
            Channel.provider == "whatsapp_cloud",
            Channel.status == "active",
        )
        .order_by(Channel.id)
        .limit(1)
    )
    channel = channel_q.scalar_one_or_none()
    if not channel:
        return None

    template_q = await db.execute(
        select(WhatsAppMessageTemplate)
        .where(
            WhatsAppMessageTemplate.seller_id == seller_id,
            WhatsAppMessageTemplate.name == "payment_reminder_v1",
            WhatsAppMessageTemplate.status == "approved",
        )
        .order_by(WhatsAppMessageTemplate.id.desc())
        .limit(1)
    )
    template = template_q.scalar_one_or_none()
    if not template:
        return None

    scheduled_at = opp.eligible_at or now
    expires_at = opp.expires_at
    if attempt.payment_expires_at and (
        not expires_at or attempt.payment_expires_at < expires_at
    ):
        expires_at = attempt.payment_expires_at
    if expires_at:
        expires_at -= timedelta(minutes=30)
        if expires_at <= scheduled_at:
            opp.status = "expired"
            opp.suppression_code = "approval_expired_before_schedule"
            await db.flush()
            return None

    action, template_params = build_bound_recovery_action(
        opportunity=opp,
        order=order,
        attempt=attempt,
        permission=permission,
        channel=channel,
        template=template,
        scheduled_at=scheduled_at,
        policy_version=policy_version,
    )
    digest = action_digest(action)
    approval = AgentApproval(
        seller_id=seller_id,
        agent_role="growth",
        action_type="payment_recovery",
        title=f"Payment recovery for order {order.id}",
        detail_json={
            "action": action,
            "digest": digest,
            "template_id": template.id,
            "template_params": template_params,
        },
        status="pending",
        order_id=order.id,
        opportunity_id=opp.id,
        action_digest=digest,
        action_revision=1,
        policy_version=policy_version,
        expected_state_version=opp.state_version + 1,
        expires_at=expires_at,
        decided_via=None,
    )
    db.add(approval)
    opp.status = "awaiting_approval"
    opp.state_version += 1
    opp.updated_at = now
    await db.flush()
    return approval

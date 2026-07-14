"""
P4.0 — Materialize current pending approval (observe -> approval transition).

- Lock seller-scoped opportunity and current facts
- If terminal or not eligible -> suppress/expire
- If eligible, build canonical action + action_revision and create awaiting_approval + pending AgentApproval in same transaction
- Partial unique ensures one pending per opportunity
- GET/list/detail remain read-only
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.payment_recovery import RevenueOpportunity, PaymentAttempt
from models.agent_os import AgentApproval
from models.order import Order
from services.payment_recovery.actions import build_canonical_action, action_digest
from services.contact_identity import hmac_fingerprint
from config import get_settings

settings = get_settings()


async def materialize_approval_for_opportunity(
    db: AsyncSession,
    *,
    seller_id: int,
    opportunity_id: uuid.UUID,
    policy_version: int = 1,
) -> AgentApproval | None:
    """
    Materialize pending recovery approval for an opportunity in approval mode.
    Returns created approval or existing pending if already materialized.
    """
    # Lock opportunity FOR UPDATE
    opp_q = await db.execute(
        select(RevenueOpportunity)
        .where(RevenueOpportunity.id == opportunity_id, RevenueOpportunity.seller_id == seller_id)
        .with_for_update()
    )
    opp = opp_q.scalar_one_or_none()
    if not opp:
        return None

    # Only materialize if detected or awaiting_approval? For P4.0, if detected -> awaiting_approval
    if opp.status not in ("detected", "awaiting_approval"):
        return None

    # Check if approval already exists pending for this opportunity (partial unique handles race, but check first)
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

    # Load current facts: order, payment attempt, etc.
    order_q = await db.execute(select(Order).where(Order.id == opp.order_id))
    order = order_q.scalar_one_or_none()
    if not order:
        return None

    attempt_q = await db.execute(select(PaymentAttempt).where(PaymentAttempt.id == opp.payment_attempt_id))
    attempt = attempt_q.scalar_one_or_none()
    if not attempt:
        return None

    # Build canonical action — simplified for MVP
    # We need contact_subject_id, permission, etc. For P4.0, we use placeholder fingerprint and channel
    # In real implementation, we would resolve contact subject via permission
    # For now, use dummy values but ensure digest is deterministic

    # Dummy contact subject and permission — in real flow, these come from ContactPermission
    # For observe mode, we may not have permission, but for approval we need active permission
    # We will try to find active permission for this order/attempt
    from models.payment_recovery import ContactPermission

    perm_q = await db.execute(
        select(ContactPermission).where(
            ContactPermission.seller_id == seller_id,
            ContactPermission.order_id == order.id,
            ContactPermission.payment_attempt_id == attempt.id,
            ContactPermission.status == "active",
        )
    )
    perm = perm_q.scalar_one_or_none()
    if not perm:
        # No active consent -> cannot materialize
        return None

    # Build fingerprints (simplified)
    recipient_fp = perm.address_fingerprint
    provider_account_fp = "provider-account-fp-placeholder"

    # Use current time for scheduled_at = eligible_at
    scheduled_at = opp.eligible_at or datetime.now(timezone.utc)

    # Ensure expiry: approval expires before opportunity expiry and payment expiry
    # For MVP, set approval expiry = min(opportunity expires, attempt expiry) - safety margin
    expires_at = opp.expires_at
    if attempt.payment_expires_at and (not expires_at or attempt.payment_expires_at < expires_at):
        expires_at = attempt.payment_expires_at
    if expires_at:
        # Safety margin 30 min
        expires_at = expires_at - timedelta(minutes=30)
        if expires_at <= scheduled_at:
            # approval_expired_before_schedule
            opp.status = "expired"
            opp.suppression_code = "approval_expired_before_schedule"
            await db.flush()
            return None

    # Build canonical action dict per spec 10.1
    # Simplified fields, but must include all required per digest
    action = build_canonical_action(
        action_version=1,
        action_type="payment_recovery",
        purpose="transactional_payment_reminder",
        seller_id=seller_id,
        opportunity_id=str(opp.id),
        order_id=order.id,
        payment_attempt_id=str(attempt.id),
        amount=Decimal(str(opp.amount_snapshot)),
        currency=opp.currency,
        payment_expires_at_utc=attempt.payment_expires_at,
        action_revision=1,
        contact_subject_id=str(perm.contact_subject_id),
        contact_permission_id=str(perm.id),
        recipient_fingerprint=recipient_fp,
        channel_id=1,  # placeholder, should be real channel_id from permission/contact
        channel_type="whatsapp",
        provider_account_fingerprint=provider_account_fp,
        provider_template_name="payment_reminder_v1",
        provider_template_locale="id",
        provider_template_content_digest="sha256-placeholder",
        provider_template_version="v1",
        template_params_digest="sha256-params",
        payment_reference_fingerprint="payment-ref-fp",
        payment_reference_fingerprint_key_version=1,
        scheduled_at_utc=scheduled_at,
        policy_version=policy_version,
    )

    digest = action_digest(action)

    # Create approval
    approval = AgentApproval(
        seller_id=seller_id,
        agent_role="growth",
        action_type="payment_recovery",
        title=f"Payment recovery for order {order.id}",
        detail_json={"action": action, "digest": digest},
        status="pending",
        order_id=order.id,
        opportunity_id=opp.id,
        action_digest=digest,
        action_revision=1,
        policy_version=policy_version,
        expected_state_version=opp.state_version,
        expires_at=expires_at,
        decided_via=None,
    )
    db.add(approval)

    # Transition opportunity to awaiting_approval
    opp.status = "awaiting_approval"
    opp.state_version += 1
    opp.updated_at = datetime.now(timezone.utc)

    try:
        await db.flush()
    except Exception as e:
        # Handle partial unique violation — another evaluator won
        await db.rollback()
        # Reload winner
        winner_q = await db.execute(
            select(AgentApproval).where(
                AgentApproval.opportunity_id == opportunity_id,
                AgentApproval.seller_id == seller_id,
                AgentApproval.status == "pending",
            )
        )
        winner = winner_q.scalar_one_or_none()
        if winner:
            return winner
        raise e

    return approval

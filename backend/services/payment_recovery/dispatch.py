"""
P4.2 — Dispatch worker and final revalidation (simplified MVP).

Sequence:
1. Domain-aware claim (already done via atomic_claim_job)
2. Load seller-scoped dispatch/opportunity/approval/order/payment/permission/channel/control/policy
3. Validate all INV-04 conditions and cap reservation
4. If fail, suppress and release reserved window
5. Commit claimed/revalidated
6. If provider current-state query needed, call outside transaction
7. Reopen tx, verify unchanged versions, atomically set BackgroundJob execution_stage side_effect_in_flight + side_effect_started_at, dispatch request_in_flight, contact window consumed, commit
8. Call send_template outside transaction
9. Conditional finalize by claim token: accepted, provider_unknown, failed_terminal, failed_retryable (only with authoritative no-write proof)
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.payment_recovery import (
    RevenueOpportunity,
    OutboundDispatch,
    RecipientContactWindow,
    PaymentAttempt,
    ContactPermission,
)
from models.agent_os import AgentApproval
from models.order import Order, OrderStatus
from models.scale_core import BackgroundJob
from core.logging_config import get_logger
from services.messaging.base import SendMessageResult

logger = get_logger(__name__)


def _classify_provider_result(result: object) -> str:
    """Classify only evidence that is explicit and stable."""
    if not isinstance(result, SendMessageResult):
        return "provider_unknown"
    message_id = result.provider_message_id
    if (
        result.success is True
        and result.outcome == "accepted"
        and isinstance(message_id, str)
        and bool(message_id.strip())
    ):
        return "accepted"
    if result.success is False and result.outcome == "rejected":
        return "rejected"
    return "provider_unknown"


async def _finalize_provider_unknown(
    db: AsyncSession,
    *,
    job: BackgroundJob,
    dispatch: OutboundDispatch,
) -> dict:
    """Persist reconciliation authority and prevent a generic resend."""
    async with db.begin():
        fresh_job_q = await db.execute(
            select(BackgroundJob).where(BackgroundJob.id == job.id)
        )
        fresh_job = fresh_job_q.scalar_one()
        if fresh_job.claim_token != job.claim_token:
            return {"success": False, "error": "stale finalize blocked"}

        dispatch.status = "provider_unknown"
        dispatch.last_error_code = "reconciliation_required"
        job.status = "dead_letter"
        job.execution_stage = "completed"
        job.retryable = False
        job.error_message = "provider outcome unknown"
        job.last_error_code = "provider_unknown"

    logger.info(
        "Payment recovery dispatch requires provider reconciliation",
        extra={"dispatch_id": str(dispatch.id), "seller_id": dispatch.seller_id},
    )
    return {
        "success": False,
        "outcome": "provider_unknown",
        "error": "provider outcome unknown",
        "error_code": "provider_unknown",
        "permanent": True,
        "retryable": False,
    }


async def revalidate_before_send(
    db: AsyncSession,
    *,
    seller_id: int,
    dispatch_id: uuid.UUID,
) -> tuple[bool, str | None]:
    """
    Re-validate all INV-04 conditions before provider call.
    Returns (allowed, suppression_code)
    """
    # Load dispatch with seller_id
    d_q = await db.execute(select(OutboundDispatch).where(OutboundDispatch.id == dispatch_id, OutboundDispatch.seller_id == seller_id))
    dispatch = d_q.scalar_one_or_none()
    if not dispatch:
        return False, "opportunity_not_found"

    # Load opportunity
    opp_q = await db.execute(select(RevenueOpportunity).where(RevenueOpportunity.id == dispatch.opportunity_id))
    opp = opp_q.scalar_one_or_none()
    if not opp or opp.seller_id != seller_id:
        return False, "opportunity_not_found"

    # Check opportunity status still dispatch_pending
    if opp.status != "dispatch_pending":
        return False, "state_changed_before_execution"

    # Load approval
    appr_q = await db.execute(select(AgentApproval).where(AgentApproval.id == dispatch.approval_id))
    approval = appr_q.scalar_one_or_none()
    if not approval or approval.seller_id != seller_id or approval.status != "approved":
        return False, "approval_stale"

    # Load order still pending and not paid
    order_q = await db.execute(select(Order).where(Order.id == opp.order_id))
    order = order_q.scalar_one_or_none()
    if not order or order.seller_id != seller_id or order.status != OrderStatus.PENDING or order.paid_at:
        return False, "already_paid" if order and order.paid_at else "order_not_pending"

    # Load payment attempt still current and not expired
    attempt_q = await db.execute(select(PaymentAttempt).where(PaymentAttempt.id == opp.payment_attempt_id))
    attempt = attempt_q.scalar_one_or_none()
    if not attempt or not attempt.is_current or (attempt.payment_expires_at and attempt.payment_expires_at <= datetime.now(timezone.utc)):
        return False, "payment_expired"

    # Load permission active
    perm_q = await db.execute(
        select(ContactPermission).where(
            ContactPermission.id == dispatch.contact_permission_id,
            ContactPermission.seller_id == seller_id,
            ContactPermission.status == "active",
        )
    )
    perm = perm_q.scalar_one_or_none()
    if not perm:
        return False, "consent_missing"

    # Check suppression active (STOP)
    from models.payment_recovery import ContactSuppression

    supp_q = await db.execute(
        select(ContactSuppression).where(
            ContactSuppression.seller_id == seller_id,
            ContactSuppression.contact_subject_id == perm.contact_subject_id,
            ContactSuppression.status == "active",
        )
    )
    supp = supp_q.scalar_one_or_none()
    if supp:
        return False, "consent_withdrawn"

    # Env + global DB kill switch + tenant pause (authoritative before side effect)
    from config import get_settings
    from models.payment_recovery import PaymentRecoveryControl
    from models.agent_os import AgentPolicy

    settings = get_settings()
    if not getattr(settings, "ENABLE_PAYMENT_RECOVERY", False):
        return False, "feature_disabled"

    control_q = await db.execute(
        select(PaymentRecoveryControl).where(PaymentRecoveryControl.id == 1)
    )
    control = control_q.scalar_one_or_none()
    if not control or not control.enabled or control.paused:
        return False, "global_paused" if (control and control.paused) else "feature_disabled"

    policy_q = await db.execute(
        select(AgentPolicy).where(AgentPolicy.seller_id == seller_id)
    )
    policy = policy_q.scalar_one_or_none()
    if not policy or getattr(policy, "payment_recovery_paused", True):
        return False, "tenant_paused"

    # All checks pass
    return True, None


async def handle_payment_recovery_dispatch(db: AsyncSession, job: BackgroundJob) -> dict:
    """
    Handler for payment_recovery_dispatch job_type.
    Implements P4.2 sequence with fenced finalize.
    """
    from services.messaging.whatsapp_cloud import WhatsAppCloudProvider
    from core.secure_config import decrypt_config
    from models.inbox import Channel

    payload = job.payload or {}
    dispatch_id_str = payload.get("dispatch_id")
    if not dispatch_id_str:
        return {"success": False, "error": "missing dispatch_id", "permanent": True}

    send_attempted = False
    try:
        dispatch_id = uuid.UUID(dispatch_id_str)
    except Exception:
        return {"success": False, "error": "invalid dispatch_id", "permanent": True}

    # 1. Revalidate
    allowed, suppression = await revalidate_before_send(db, seller_id=job.seller_id, dispatch_id=dispatch_id)
    if not allowed:
        # Suppress and release reserved window (pre-network)
        # Load dispatch and window
        d_q = await db.execute(select(OutboundDispatch).where(OutboundDispatch.id == dispatch_id))
        dispatch = d_q.scalar_one_or_none()
        if dispatch:
            # Find reserved window for this opportunity
            w_q = await db.execute(
                select(RecipientContactWindow).where(
                    RecipientContactWindow.opportunity_id == dispatch.opportunity_id,
                    RecipientContactWindow.status == "reserved",
                )
            )
            window = w_q.scalar_one_or_none()
            if window:
                window.status = "released"
                window.released_at = datetime.now(timezone.utc)
                window.release_reason = suppression

            dispatch.status = "cancelled"
            dispatch.last_error_code = suppression

            # Also transition opportunity to suppressed if needed
            opp_q = await db.execute(select(RevenueOpportunity).where(RevenueOpportunity.id == dispatch.opportunity_id))
            opp = opp_q.scalar_one_or_none()
            if opp and opp.status == "dispatch_pending":
                opp.status = "suppressed"
                opp.suppression_code = suppression
                opp.state_version += 1

            await db.commit()

        return {"success": False, "error": suppression, "permanent": True, "reason": suppression}

    # 2. Commit claimed/revalidated (already claimed via atomic_claim_job, but we set status to claimed)
    # For MVP, we assume claim already done, now set to request_in_flight

    # Load dispatch again
    d_q = await db.execute(select(OutboundDispatch).where(OutboundDispatch.id == dispatch_id))
    dispatch = d_q.scalar_one_or_none()
    if not dispatch:
        return {"success": False, "error": "dispatch not found", "permanent": True}

    # Atomically set request_in_flight and side_effect_in_flight, consumed window
    # This should be done in a new transaction before network call
    try:
        # Set dispatch request_in_flight
        dispatch.status = "request_in_flight"
        dispatch.attempt_count += 1

        # Set job execution_stage side_effect_in_flight
        job.execution_stage = "side_effect_in_flight"
        job.side_effect_started_at = datetime.now(timezone.utc)
        await db.commit()

        # Set window consumed
        w_q = await db.execute(
            select(RecipientContactWindow).where(
                RecipientContactWindow.opportunity_id == dispatch.opportunity_id,
                RecipientContactWindow.status == "reserved",
            )
        )
        window = w_q.scalar_one_or_none()
        if window:
            window.status = "consumed"
            window.consumed_at = datetime.now(timezone.utc)
            await db.commit()

    except Exception as exc:
        await db.rollback()
        logger.warning(
            "Payment recovery pre-send state could not be persisted",
            extra={
                "dispatch_id": str(dispatch.id),
                "seller_id": dispatch.seller_id,
                "error_type": type(exc).__name__,
            },
        )
        return {
            "success": False,
            "outcome": "not_sent",
            "error": "failed to persist pre-send state",
            "error_code": "pre_send_state_not_persisted",
            "permanent": True,
            "retryable": False,
        }

    # 3. Call provider outside transaction
    # Load channel
    channel_q = await db.execute(select(Channel).where(Channel.id == dispatch.channel_id))
    channel = channel_q.scalar_one_or_none()
    await db.commit()

    if not channel:
        # Terminal failure
        async with db.begin():
            dispatch.status = "failed_terminal"
            dispatch.last_error_code = "provider_unavailable"
            job.status = "done"
            job.execution_stage = "completed"
        return {"success": False, "error": "channel not found", "permanent": True}

    try:
        from core.secure_config import decrypt_config

        cfg = decrypt_config(channel.config_encrypted)
        provider = WhatsAppCloudProvider(
            access_token=cfg.get("access_token", ""),
            phone_number_id=cfg.get("phone_number_id", channel.external_id),
            app_secret=cfg.get("app_secret", ""),
        )

        recipient_phone = None
        try:
            from models.payment_recovery import ContactSubject
            from services.contact_identity import decrypt_address

            subj_q = await db.execute(
                select(ContactSubject).where(ContactSubject.id == dispatch.contact_subject_id)
            )
            subj = subj_q.scalar_one_or_none()
            if subj and subj.address_ciphertext:
                decrypted = decrypt_address(subj.address_ciphertext, subj.address_key_version)
                if decrypted:
                    recipient_phone = decrypted
        except Exception:
            recipient_phone = None

        # SQLAlchemy autobegins for the channel/contact reads above. End that
        # read transaction before crossing the provider network boundary.
        await db.commit()

        if not recipient_phone:
            # No network write occurred; mark terminal failure without claiming send.
            try:
                async with db.begin():
                    fresh_job_q = await db.execute(
                        select(BackgroundJob).where(BackgroundJob.id == job.id)
                    )
                    fresh_job = fresh_job_q.scalar_one()
                    if fresh_job.claim_token != job.claim_token:
                        return {"success": False, "error": "stale finalize blocked"}
                    dispatch.status = "failed_terminal"
                    dispatch.last_error_code = "recipient_unavailable"
                    job.status = "dead_letter"
                    job.execution_stage = "completed"
                    job.retryable = False
                    job.error_message = "recipient unavailable"
                    job.last_error_code = "recipient_unavailable"
            except Exception:
                await db.rollback()
            return {
                "success": False,
                "outcome": "not_sent",
                "error": "recipient unavailable",
                "error_code": "recipient_unavailable",
                "permanent": True,
                "retryable": False,
            }

        template_params = []
        if isinstance(dispatch.template_params_json, dict):
            raw_params = dispatch.template_params_json.get("body") or dispatch.template_params_json.get("parameters")
            if isinstance(raw_params, list):
                template_params = [str(p) for p in raw_params]
        language_code = "id"
        if isinstance(dispatch.template_params_json, dict):
            language_code = str(dispatch.template_params_json.get("language") or "id")

        send_attempted = True
        # P4.4 — exact utility template send; free-form text is not used for recovery.
        send_result = await provider.send_template(
            recipient_phone,
            template_name=str(dispatch.template_code or "").strip().lower(),
            language_code=language_code,
            body_parameters=template_params,
            expected_parameter_count=len(template_params) if template_params else 0,
        )
        send_outcome = _classify_provider_result(send_result)

        # 4. Conditional finalize by claim token
        if send_outcome == "accepted":
            # Accepted
            async with db.begin():
                # Verify claim token still matches job's current token (fencing)
                fresh_job_q = await db.execute(select(BackgroundJob).where(BackgroundJob.id == job.id))
                fresh_job = fresh_job_q.scalar_one()
                if fresh_job.claim_token != job.claim_token:
                    return {"success": False, "error": "stale finalize blocked"}

                dispatch.status = "accepted"
                dispatch.accepted_at = datetime.now(timezone.utc)
                dispatch.provider_message_id = send_result.provider_message_id
                job.status = "done"
                job.execution_stage = "completed"
                job.retryable = False
                job.finished_at = datetime.now(timezone.utc)

                # Transition opportunity to dispatched
                opp_q = await db.execute(select(RevenueOpportunity).where(RevenueOpportunity.id == dispatch.opportunity_id))
                opp = opp_q.scalar_one_or_none()
                if opp:
                    opp.status = "dispatched"
                    opp.state_version += 1

            return {
                "success": True,
                "outcome": "accepted",
                "provider_message_id": send_result.provider_message_id,
            }

        if send_outcome == "rejected":
            # Provider rejected -> terminal failure
            async with db.begin():
                fresh_job_q = await db.execute(select(BackgroundJob).where(BackgroundJob.id == job.id))
                fresh_job = fresh_job_q.scalar_one()
                if fresh_job.claim_token != job.claim_token:
                    return {"success": False, "error": "stale finalize blocked"}

                dispatch.status = "failed_terminal"
                dispatch.last_error_code = "provider_rejected"
                job.status = "dead_letter"
                job.execution_stage = "completed"
                job.retryable = False
                job.error_message = "provider rejected"
                job.last_error_code = "provider_rejected"

                # Opportunity suppressed with terminal reason
                opp_q = await db.execute(select(RevenueOpportunity).where(RevenueOpportunity.id == dispatch.opportunity_id))
                opp = opp_q.scalar_one_or_none()
                if opp:
                    opp.status = "suppressed"
                    opp.terminal_reason_code = "dispatch_provider_rejected"
                    opp.state_version += 1

            return {
                "success": False,
                "outcome": "rejected",
                "error": "provider rejected",
                "error_code": "provider_rejected",
                "permanent": True,
                "retryable": False,
            }

        return await _finalize_provider_unknown(
            db,
            job=job,
            dispatch=dispatch,
        )

    except Exception as e:
        if send_attempted:
            try:
                return await _finalize_provider_unknown(
                    db,
                    job=job,
                    dispatch=dispatch,
                )
            except Exception:
                await db.rollback()
                return {
                    "success": False,
                    "outcome": "provider_unknown",
                    "error": "provider outcome unknown and evidence was not persisted",
                    "error_code": "provider_unknown_evidence_not_persisted",
                    "permanent": True,
                    "retryable": False,
                }

        # The provider method was never invoked, so this is a pre-send terminal
        # configuration/dependency failure rather than an ambiguous write.
        try:
            await db.rollback()
            async with db.begin():
                dispatch.status = "failed_terminal"
                dispatch.last_error_code = "provider_unavailable"
                job.status = "dead_letter"
                job.execution_stage = "completed"
                job.retryable = False
                job.error_message = "provider unavailable before send"
                job.last_error_code = "provider_unavailable"
        except Exception:
            await db.rollback()

        return {
            "success": False,
            "outcome": "not_sent",
            "error": "provider unavailable before send",
            "error_code": "provider_unavailable",
            "permanent": True,
            "retryable": False,
        }

"""
P4.1 — Recovery approval service atomic.

Implements POST approve algorithm per blueprint 31.3 with idempotency receipt,
fenced dispatch, cap reservation.

Simplified for MVP but preserves core invariants:
- Seller-scoped lookup with FOR UPDATE
- Idempotency key same hash replay, different hash 409
- Different key after win -> approval_already_used 409
- Exact digest constant-time compare
- Cap reservation via RecipientContactWindow
- Atomic creation of approval used_at, dispatch, job, opportunity transition
- Decision receipt persisted
"""
from __future__ import annotations
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from models.inbox import Channel
from models.wa_template import WhatsAppMessageTemplate
from models.payment_recovery import (
    RevenueOpportunity,
    PaymentAttempt,
    ContactPermission,
    RecipientContactWindow,
    OutboundDispatch,
)
from models.agent_os import AgentApproval
from models.order import Order
from services.payment_recovery.actions import action_digest
from services.payment_recovery.approval_materializer import build_bound_recovery_action
import json as json_lib


def hash_decision_request(request_body: dict) -> str:
    """Hash decision request for idempotency conflict detection."""
    canonical = json_lib.dumps(request_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


async def find_decision_receipt(
    db: AsyncSession,
    *,
    seller_id: int,
    decision_scope: str,
    opportunity_id: uuid.UUID,
    idempotency_key: str,
):
    q = await db.execute(
        select(AgentApproval).where(
            AgentApproval.seller_id == seller_id,
            AgentApproval.decision_scope == decision_scope,
            AgentApproval.opportunity_id == opportunity_id,
            AgentApproval.decision_idempotency_key == idempotency_key,
        )
    )
    return q.scalar_one_or_none()


def replay_same_hash_or_raise_conflict(replay, request_hash: str):
    if replay.decision_request_hash == request_hash:
        # Return durable response snapshot
        return replay.decision_response_json
    else:
        raise HTTPException(status_code=409, detail={"error": "idempotency_conflict", "message": "Idempotency key sudah dipakai dengan payload berbeda"})


async def approve_recovery(
    db: AsyncSession,
    *,
    principal_seller_id: int,
    opportunity_id: uuid.UUID,
    expected_version: int,
    action_digest_from_client: str,
    idempotency_key: str,
    request_body: dict,
):
    """
    Atomic approve transaction per blueprint.
    """
    decision_scope = "recovery.approve"
    request_hash = hash_decision_request(request_body)

    # 1. Check completed receipt by key (before lock)
    replay = await find_decision_receipt(
        db,
        seller_id=principal_seller_id,
        decision_scope=decision_scope,
        opportunity_id=opportunity_id,
        idempotency_key=idempotency_key,
    )
    if replay:
        # Same hash replay, different hash conflict
        if replay.decision_request_hash == request_hash:
            return replay.decision_response_json
        else:
            raise HTTPException(status_code=409, detail={"error": "idempotency_conflict"})

    # 2. Lock opportunity and approval FOR UPDATE
    # Load opportunity FOR UPDATE
    opp_q = await db.execute(
        select(RevenueOpportunity)
        .where(RevenueOpportunity.id == opportunity_id, RevenueOpportunity.seller_id == principal_seller_id)
        .with_for_update()
    )
    opportunity = opp_q.scalar_one_or_none()
    if not opportunity:
        raise HTTPException(status_code=404, detail={"error": "opportunity_not_found"})

    # Load latest matching recovery approval FOR UPDATE without status predicate
    approval_q = await db.execute(
        select(AgentApproval)
        .where(AgentApproval.opportunity_id == opportunity_id, AgentApproval.seller_id == principal_seller_id)
        .order_by(AgentApproval.id.desc())
        .with_for_update()
    )
    approval = approval_q.scalars().first()
    if not approval:
        raise HTTPException(status_code=404, detail={"error": "approval_not_found"})

    # 3. Re-read receipt after lock to serialize races
    locked_replay = await find_decision_receipt(
        db,
        seller_id=principal_seller_id,
        decision_scope=decision_scope,
        opportunity_id=opportunity_id,
        idempotency_key=idempotency_key,
    )
    if locked_replay:
        if locked_replay.decision_request_hash == request_hash:
            return locked_replay.decision_response_json
        else:
            raise HTTPException(status_code=409, detail={"error": "idempotency_conflict"})

    # 4. Bind decision intent on locked approval
    approval.decision_scope = decision_scope
    approval.decision_idempotency_key = idempotency_key
    approval.decision_request_hash = request_hash
    await db.flush()

    # 5. Require pending current
    if approval.status != "pending":
        # Check if already used
        if approval.used_at:
            raise HTTPException(status_code=409, detail={"error": "approval_already_used", "message": "Persetujuan sudah dipakai"})
        raise HTTPException(status_code=409, detail={"error": "approval_stale", "message": "Persetujuan tidak lagi pending"})

    if opportunity.state_version != expected_version:
        raise HTTPException(status_code=409, detail={"error": "approval_stale", "current_version": opportunity.state_version})

    # Check expiry
    now = datetime.now(timezone.utc)
    if approval.expires_at and approval.expires_at < now:
        raise HTTPException(status_code=410, detail={"error": "approval_expired"})

    # 6. Rebuild the exact action from seller-scoped current facts.
    order_q = await db.execute(
        select(Order).where(
            Order.id == opportunity.order_id,
            Order.seller_id == principal_seller_id,
        )
    )
    order = order_q.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail={"error": "order_not_found"})

    attempt_q = await db.execute(
        select(PaymentAttempt).where(
            PaymentAttempt.id == opportunity.payment_attempt_id,
            PaymentAttempt.order_id == order.id,
            PaymentAttempt.seller_id == principal_seller_id,
            PaymentAttempt.is_current.is_(True),
        )
    )
    attempt = attempt_q.scalar_one_or_none()
    if not attempt:
        raise HTTPException(status_code=409, detail={"error": "approval_stale"})

    permission_q = await db.execute(
        select(ContactPermission).where(
            ContactPermission.seller_id == principal_seller_id,
            ContactPermission.order_id == order.id,
            ContactPermission.payment_attempt_id == attempt.id,
            ContactPermission.channel == "whatsapp",
            ContactPermission.purpose == "transactional_payment_reminder",
            ContactPermission.scope_type == "order_payment_cycle",
            ContactPermission.status == "active",
            or_(ContactPermission.expires_at.is_(None), ContactPermission.expires_at > now),
        )
    )
    permission = permission_q.scalar_one_or_none()
    if not permission:
        raise HTTPException(status_code=409, detail={"error": "consent_missing", "message": "Izin tidak aktif"})

    existing_detail = approval.detail_json or {}
    existing_action = existing_detail.get("action")
    if not isinstance(existing_action, dict):
        raise HTTPException(status_code=409, detail={"error": "approval_stale"})

    channel_q = await db.execute(
        select(Channel).where(
            Channel.id == existing_action.get("channel_id"),
            Channel.seller_id == principal_seller_id,
            Channel.type == existing_action.get("channel_type"),
            Channel.provider == "whatsapp_cloud",
            Channel.status == "active",
        )
    )
    channel = channel_q.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=409, detail={"error": "approval_stale", "message": "Channel berubah"})

    template_q = await db.execute(
        select(WhatsAppMessageTemplate).where(
            WhatsAppMessageTemplate.id == existing_detail.get("template_id"),
            WhatsAppMessageTemplate.seller_id == principal_seller_id,
            WhatsAppMessageTemplate.name == existing_action.get("provider_template_name"),
            WhatsAppMessageTemplate.language == existing_action.get("provider_template_locale"),
            WhatsAppMessageTemplate.status == "approved",
        )
    )
    template = template_q.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=409, detail={"error": "approval_stale", "message": "Template berubah"})

    fresh_action, template_params = build_bound_recovery_action(
        opportunity=opportunity,
        order=order,
        attempt=attempt,
        permission=permission,
        channel=channel,
        template=template,
        scheduled_at=existing_action.get("scheduled_at_utc"),
        policy_version=approval.policy_version,
    )
    fresh_digest = action_digest(fresh_action)
    expected_digest = approval.action_digest
    if not (
        constant_time_compare(fresh_digest, expected_digest)
        and constant_time_compare(action_digest_from_client, expected_digest)
    ):
        raise HTTPException(status_code=409, detail={"error": "approval_stale", "message": "Digest tidak cocok, data berubah"})

    # 8. Acquire a process-stable advisory lock and recheck the cap
    lock_material = (
        f"{principal_seller_id}:{permission.contact_subject_id}:"
        "transactional_payment_reminder"
    ).encode("utf-8")
    lock_key = int.from_bytes(
        hashlib.sha256(lock_material).digest()[:8], "big", signed=True
    )
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})

    # Check rolling cap: count reserved + consumed in last 24h for same subject
    cap_check_sql = text(
        """
        SELECT COUNT(*) FROM recipient_contact_windows
        WHERE seller_id=:seller_id
          AND contact_subject_id=:subject_id
          AND purpose='transactional_payment_reminder'
          AND status IN ('reserved','consumed')
          AND window_started_at >= now() - interval '24 hours'
        """
    )
    cap_result = await db.execute(
        cap_check_sql, {"seller_id": principal_seller_id, "subject_id": str(permission.contact_subject_id)}
    )
    count = cap_result.scalar() or 0
    # Daily cap = 1 per MVP
    if count >= 1:
        raise HTTPException(status_code=409, detail={"error": "frequency_cap_reached"})

    # 9. Reserve contact window
    window = RecipientContactWindow(
        seller_id=principal_seller_id,
        contact_subject_id=permission.contact_subject_id,
        purpose="transactional_payment_reminder",
        opportunity_id=opportunity.id,
        window_started_at=now,
        window_ends_at=now + timedelta(hours=24),
        status="reserved",
        reserved_at=now,
        expires_at=now + timedelta(hours=24),
    )
    db.add(window)
    await db.flush()

    # 10. Consume approval
    approval.status = "approved"
    approval.used_at = now
    approval.decided_at = now

    # 11. Create logical OutboundDispatch
    dispatch_id = uuid.uuid4()
    idempotency_key_dispatch = f"payment-recovery:v1:{principal_seller_id}:{order.id}:{attempt.id}"

    dispatch = OutboundDispatch(
        id=dispatch_id,
        seller_id=principal_seller_id,
        opportunity_id=opportunity.id,
        approval_id=approval.id,
        channel_id=channel.id,
        channel_type=channel.type,
        status="scheduled",
        delivery_status="not_available",
        template_code=template.name,
        template_params_json=template_params,
        action_digest=expected_digest,
        contact_permission_id=permission.id,
        contact_subject_id=permission.contact_subject_id,
        recipient_fingerprint=permission.address_fingerprint,
        idempotency_key=idempotency_key_dispatch,
        provider=channel.provider,
        scheduled_at=now,
    )
    db.add(dispatch)
    await db.flush()

    # 12. Create durable BackgroundJob
    from core.idempotency import enqueue_job_record

    job_payload = {
        "dispatch_id": str(dispatch.id),
        "opportunity_id": str(opportunity.id),
        "order_id": order.id,
        "payment_attempt_id": str(attempt.id),
    }
    job_idem_key = f"dispatch:{dispatch.id}"
    job, _ = await enqueue_job_record(
        db,
        job_type="payment_recovery_dispatch",
        payload=job_payload,
        seller_id=principal_seller_id,
        idempotency_key=job_idem_key,
        handler_contract_version=1,
        max_attempts=5,
        retryable=False,
    )
    await db.flush()

    # Link job to dispatch
    dispatch.background_job_id = job.id

    # 13. Transition opportunity
    opportunity.status = "dispatch_pending"
    opportunity.state_version += 1
    opportunity.updated_at = now
    await db.flush()

    # 14. Finalize receipt
    response_snapshot = {
        "approval": {"id": approval.id, "status": "approved", "used_at": now.isoformat()},
        "opportunity": {"id": str(opportunity.id), "status": opportunity.status, "state_version": opportunity.state_version},
        "dispatch": {"id": str(dispatch.id), "status": dispatch.status, "scheduled_at": dispatch.scheduled_at.isoformat() if dispatch.scheduled_at else None},
        "message": "Disetujui, menunggu pemeriksaan terakhir.",
    }

    approval.decision_response_json = response_snapshot
    await db.flush()
    await db.commit()

    # The durable database queue is the source of truth. The poller will claim this job.
    return response_snapshot

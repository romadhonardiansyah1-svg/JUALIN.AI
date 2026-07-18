"""
Background job handlers for the ARQ worker.

Each handler processes a specific job_type from the background_jobs table.
Handlers are dispatched by job_type in worker.process_recorded_job.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from core.logging_config import get_logger
from models.inbox import Channel, ChannelContact, InboxThread, InboxMessage
from models.crm import Customer
from models.order import Order, OrderStatus
from models.campaign import Campaign, CampaignRecipient, CampaignMessage
from models.ai_quality import AITrace
from models.scale_core import BackgroundJob
from core.secure_config import decrypt_config
from services.messaging.base import SendMessageResult
from services.messaging.whatsapp_cloud import WhatsAppCloudProvider
from services.customer_resolver import resolve_customer

settings = get_settings()
logger = get_logger(__name__)


# ════════════════════════════════════════════════
# Handler: inbox_ai_reply
# ════════════════════════════════════════════════

async def handle_inbox_ai_reply(db: AsyncSession, job: BackgroundJob) -> dict:
    """
    Process an AI reply for an inbox thread.
    Payload: {"thread_id": int, "message_id": "wamid.xxx"}
    """
    thread_id = job.payload.get("thread_id")
    inbound_message_id = job.payload.get("message_id", "")

    if not thread_id:
        return {"success": False, "error": "missing thread_id"}

    # Load thread with channel and contact
    result = await db.execute(
        select(InboxThread, Channel, ChannelContact)
        .join(Channel, InboxThread.channel_id == Channel.id)
        .join(ChannelContact, InboxThread.contact_id == ChannelContact.id)
        .where(InboxThread.id == thread_id)
    )
    row = result.first()
    if not row:
        return {"success": False, "error": "thread not found"}

    thread, channel, contact = row

    # ── Check mode before generating ──
    if thread.mode != "ai":
        return {"success": True, "skipped": True, "reason": "thread mode is manual"}

    # Load inbound message
    inbound_msg = None
    if inbound_message_id:
        msg_result = await db.execute(
            select(InboxMessage)
            .where(InboxMessage.external_message_id == inbound_message_id)
            .where(InboxMessage.thread_id == thread.id)
        )
        inbound_msg = msg_result.scalar_one_or_none()

    if not inbound_msg:
        # Load latest inbound
        msg_result = await db.execute(
            select(InboxMessage)
            .where(InboxMessage.thread_id == thread.id)
            .where(InboxMessage.direction == "inbound")
            .order_by(InboxMessage.created_at.desc())
            .limit(1)
        )
        inbound_msg = msg_result.scalar_one_or_none()

    if not inbound_msg:
        return {"success": False, "error": "no inbound message found"}

    # Build conversation history from last 20 messages
    history_result = await db.execute(
        select(InboxMessage)
        .where(InboxMessage.thread_id == thread.id)
        .order_by(InboxMessage.created_at.desc())
        .limit(20)
    )
    history_messages = list(reversed(history_result.scalars().all()))

    # Format as chat history
    conversation_history = []
    for msg in history_messages:
        role = "user" if msg.direction == "inbound" else "assistant"
        conversation_history.append({"role": role, "content": msg.content})

    # Resolve customer
    customer = None
    try:
        customer, _ = await resolve_customer(
            db,
            seller_id=channel.seller_id,
            phone=contact.phone or contact.external_id,
            whatsapp_id=contact.external_id,
            session_id=f"wa:{contact.external_id}",
            name=contact.name or "Customer",
        )
    except Exception as e:
        logger.warning(f"Customer resolve failed for inbox AI reply: {e}")

    # ── Double-check mode before generation ──
    await db.refresh(thread)
    if thread.mode != "ai":
        return {"success": True, "skipped": True, "reason": "thread mode changed to manual"}

    # Generate AI response
    ai_text = ""
    intent = "general"
    sales_stage = "greeting"
    structured_actions_results = []

    try:
        if settings.ENABLE_AI_ACTIONS:
            from ai.agent import get_ai_structured_response
            try:
                structured, intent, sales_stage = await get_ai_structured_response(
                    message=inbound_msg.content,
                    seller_id=channel.seller_id,
                    conversation_history=conversation_history,
                    seller_style="santai",
                    db=db,
                )
                ai_text = structured.reply

                # Execute actions
                if structured.actions:
                    from ai.actions import execute_ai_actions
                    structured_actions_results = await execute_ai_actions(
                        seller_id=channel.seller_id,
                        actions=structured.actions,
                        db=db,
                        actor="ai",
                        user_message=inbound_msg.content,
                    )
                    # Append payment link if order was created
                    for ar in structured_actions_results:
                        if ar.get("type") == "create_order" and ar.get("success") and ar.get("payment_url"):
                            ai_text += f"\n\nLink pembayaran: {ar['payment_url']}"
            except (ValueError, Exception) as e:
                logger.warning(f"Structured AI failed, falling back: {e}")
                ai_text = ""

        if not ai_text:
            from ai.agent import get_ai_response
            ai_text, intent, sales_stage = await get_ai_response(
                message=inbound_msg.content,
                seller_id=channel.seller_id,
                conversation_history=conversation_history,
                seller_style="santai",
                db=db,
            )
    except Exception as e:
        logger.error(f"AI generation failed: {e}", exc_info=True)
        ai_text = "Maaf kak, saat ini kami sedang mengalami kendala teknis. Silakan coba lagi nanti ya 🙏"

    if not ai_text:
        ai_text = "Hai kak! Ada yang bisa kami bantu? 😊"

    # ── Send WhatsApp reply ──
    send_status = "sent"
    provider_message_id = ""
    send_error = ""

    config = decrypt_config(channel.config_encrypted)
    provider = WhatsAppCloudProvider(
        access_token=config.get("access_token", ""),
        phone_number_id=config.get("phone_number_id", channel.external_id),
        app_secret=config.get("app_secret", ""),
    )

    if not provider.access_token or not provider.phone_number_id:
        send_status = "failed"
        send_error = "WhatsApp credentials not configured"
        logger.warning(f"WhatsApp not configured for channel {channel.id}, skipping send")
    else:
        try:
            send_result = await provider.send_message(
                contact.phone or contact.external_id,
                ai_text,
            )
            if send_result.success:
                provider_message_id = send_result.provider_message_id
            else:
                send_status = "failed"
                send_error = send_result.error_message
        except Exception as e:
            send_status = "failed"
            send_error = str(e)

    # ── Save outbound message ──
    outbound = InboxMessage(
        seller_id=channel.seller_id,
        thread_id=thread.id,
        direction="outbound",
        role="ai",
        content=ai_text,
        status=send_status,
        external_message_id=provider_message_id,
    )
    db.add(outbound)

    # Update thread
    thread.last_message_preview = ai_text[:500]
    thread.last_message_at = datetime.now(timezone.utc)
    if thread.unread_count and thread.unread_count > 0:
        thread.unread_count = max(0, thread.unread_count - 1)
    if sales_stage and sales_stage != "greeting":
        thread.stage = sales_stage

    # ── Record AI trace ──
    trace = AITrace(
        seller_id=channel.seller_id,
        trace_id=f"inbox:{uuid.uuid4().hex[:16]}",
        provider="llm",
        model=settings.LLM_MODEL,
        stage=sales_stage,
        status="ok" if send_status == "sent" else "error",
        prompt_preview=inbound_msg.content[:500],
        response_preview=ai_text[:500],
        metadata_json={
            "thread_id": thread.id,
            "intent": intent,
            "actions": [r.get("type") for r in structured_actions_results],
            "send_status": send_status,
        },
    )
    db.add(trace)
    await db.commit()

    if send_status == "failed":
        # Credential errors should not retry
        if "not configured" in send_error.lower() or "credential" in send_error.lower():
            return {"success": False, "error": send_error, "permanent": True}
        return {"success": False, "error": send_error}

    return {"success": True, "thread_id": thread.id, "message_id": provider_message_id}


# ════════════════════════════════════════════════
# Handler: pending_payment_followup
# ════════════════════════════════════════════════

def _followup_failure(
    *,
    outcome: str,
    reason: str,
    error: str,
    error_code: str,
) -> dict[str, object]:
    """Build the terminal, non-retryable result understood by the legacy worker."""
    return {
        "success": False,
        "outcome": outcome,
        "reason": reason,
        "error": error,
        "error_code": error_code,
        "permanent": True,
        "retryable": False,
    }


def _classify_followup_send(result: object) -> str:
    """Map the additive provider contract to accepted/rejected/unknown."""
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


async def handle_pending_payment_followup(db: AsyncSession, job: BackgroundJob) -> dict:
    """Process one contained legacy follow-up without false success or tenant drift."""
    from ai.followup import FOLLOWUP_MESSAGES, mark_followup_sent

    job_id = getattr(job, "id", None)
    seller_id = getattr(job, "seller_id", None)
    if not (
        getattr(settings, "ENABLE_LEGACY_PENDING_PAYMENT_FOLLOWUP", False)
        and getattr(settings, "ENABLE_WHATSAPP", False)
    ):
        logger.info(
            "Legacy follow-up job suppressed by disabled outbound flags",
            extra={"job_id": job_id, "seller_id": seller_id},
        )
        return _followup_failure(
            outcome="not_sent",
            reason="legacy_followup_disabled",
            error="legacy followup disabled",
            error_code="legacy_followup_disabled",
        )

    payload = getattr(job, "payload", None)
    order_id = payload.get("order_id") if isinstance(payload, dict) else None
    if type(order_id) is not int or order_id <= 0:
        return _followup_failure(
            outcome="suppressed",
            reason="invalid_order_reference",
            error="invalid order reference",
            error_code="invalid_order_reference",
        )
    if type(seller_id) is not int or seller_id <= 0:
        return _followup_failure(
            outcome="suppressed",
            reason="invalid_seller_reference",
            error="invalid seller reference",
            error_code="invalid_seller_reference",
        )

    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.seller_id == seller_id)
    )
    order = result.scalar_one_or_none()

    if not order:
        logger.warning(
            "Followup job order not found or tenant mismatch",
            extra={"job_id": job_id, "order_id": order_id, "seller_id": seller_id},
        )
        return _followup_failure(
            outcome="suppressed",
            reason="order_not_found_or_tenant_mismatch",
            error="order not found",
            error_code="order_not_found",
        )

    if order.seller_id != seller_id:
        logger.error(
            "Followup job database result violated tenant ownership",
            extra={"job_id": job_id, "order_id": order_id, "seller_id": seller_id},
        )
        return _followup_failure(
            outcome="suppressed",
            reason="cross_tenant_reference",
            error="order not found",
            error_code="cross_tenant_reference",
        )

    if order.status != OrderStatus.PENDING:
        return {
            "success": True,
            "outcome": "not_sent",
            "skipped": True,
            "reason": "order_no_longer_pending",
        }

    followup_num = min(order.followup_count, 2)
    message = FOLLOWUP_MESSAGES[followup_num]
    items_text = order.items if isinstance(order.items, str) else str(order.items)
    message += f"\n\n📋 Detail order:\n{items_text}\n💰 Total: Rp {order.total:,.0f}"

    if not order.customer_phone:
        return _followup_failure(
            outcome="not_sent",
            reason="recipient_missing",
            error="recipient missing",
            error_code="recipient_missing",
        )

    channel_result = await db.execute(
        select(Channel)
        .where(Channel.seller_id == order.seller_id)
        .where(Channel.type == "whatsapp")
        .where(Channel.provider == "whatsapp_cloud")
        .where(Channel.status == "active")
        .limit(1)
    )
    channel = channel_result.scalar_one_or_none()
    if not channel:
        logger.info(
            "Legacy follow-up not sent because no active channel is available",
            extra={"order_id": order.id, "seller_id": order.seller_id},
        )
        return _followup_failure(
            outcome="not_sent",
            reason="simulated_not_sent",
            error="channel unavailable",
            error_code="channel_unavailable",
        )

    try:
        config = decrypt_config(channel.config_encrypted)
    except Exception as exc:
        logger.warning(
            "Legacy follow-up provider configuration could not be decrypted",
            extra={
                "job_id": job_id,
                "order_id": order.id,
                "seller_id": order.seller_id,
                "error_type": type(exc).__name__,
            },
        )
        return _followup_failure(
            outcome="not_sent",
            reason="provider_configuration_unavailable",
            error="provider configuration unavailable",
            error_code="provider_configuration_unavailable",
        )

    if not isinstance(config, dict):
        config = {}
    access_token = config.get("access_token")
    phone_number_id = config.get("phone_number_id") or channel.external_id
    if not (
        isinstance(access_token, str)
        and bool(access_token.strip())
        and isinstance(phone_number_id, str)
        and bool(phone_number_id.strip())
    ):
        logger.info(
            "Legacy follow-up not sent because the tenant channel is not configured",
            extra={"order_id": order.id, "seller_id": order.seller_id},
        )
        return _followup_failure(
            outcome="not_sent",
            reason="simulated_not_sent",
            error="channel not configured",
            error_code="channel_not_configured",
        )

    try:
        provider = WhatsAppCloudProvider(
            access_token=access_token,
            phone_number_id=phone_number_id,
            app_secret=config.get("app_secret", ""),
        )
    except Exception as exc:
        logger.warning(
            "Legacy follow-up provider could not be initialized",
            extra={
                "job_id": job_id,
                "order_id": order.id,
                "seller_id": order.seller_id,
                "error_type": type(exc).__name__,
            },
        )
        return _followup_failure(
            outcome="not_sent",
            reason="provider_configuration_unavailable",
            error="provider configuration unavailable",
            error_code="provider_configuration_unavailable",
        )

    try:
        send_result = await provider.send_message(order.customer_phone, message)
    except Exception as exc:
        logger.warning(
            "Legacy follow-up provider outcome is unknown",
            extra={
                "job_id": job_id,
                "order_id": order.id,
                "seller_id": order.seller_id,
                "error_type": type(exc).__name__,
            },
        )
        return _followup_failure(
            outcome="provider_unknown",
            reason="provider_unknown",
            error="provider outcome unknown",
            error_code="provider_unknown",
        )

    send_outcome = _classify_followup_send(send_result)
    if send_outcome == "rejected":
        logger.warning(
            "Legacy follow-up provider rejected the request",
            extra={"job_id": job_id, "order_id": order.id, "seller_id": order.seller_id},
        )
        return _followup_failure(
            outcome="rejected",
            reason="provider_rejected",
            error="provider rejected",
            error_code="provider_rejected",
        )
    if send_outcome != "accepted":
        logger.warning(
            "Legacy follow-up provider outcome is unknown",
            extra={"job_id": job_id, "order_id": order.id, "seller_id": order.seller_id},
        )
        return _followup_failure(
            outcome="provider_unknown",
            reason="provider_unknown",
            error="provider outcome unknown",
            error_code="provider_unknown",
        )

    try:
        marked = await mark_followup_sent(order.id, order.seller_id, db)
    except Exception as exc:
        await db.rollback()
        logger.error(
            "Accepted legacy follow-up evidence could not be persisted",
            extra={
                "job_id": job_id,
                "order_id": order.id,
                "seller_id": order.seller_id,
                "error_type": type(exc).__name__,
            },
        )
        failure = _followup_failure(
            outcome="accepted",
            reason="accepted_evidence_not_persisted",
            error="accepted evidence not persisted",
            error_code="accepted_evidence_not_persisted",
        )
        failure["provider_message_id"] = send_result.provider_message_id
        return failure

    if marked is not True:
        logger.error(
            "Accepted legacy follow-up evidence did not match the tenant order",
            extra={"job_id": job_id, "order_id": order.id, "seller_id": order.seller_id},
        )
        failure = _followup_failure(
            outcome="accepted",
            reason="accepted_evidence_not_persisted",
            error="accepted evidence not persisted",
            error_code="accepted_evidence_not_persisted",
        )
        failure["provider_message_id"] = send_result.provider_message_id
        return failure

    return {
        "success": True,
        "outcome": "accepted",
        "order_id": order.id,
        "sent_via": "whatsapp",
        "provider_message_id": send_result.provider_message_id,
    }


# ════════════════════════════════════════════════
# Handler: campaign_send_message
# ════════════════════════════════════════════════

async def handle_campaign_send_message(db: AsyncSession, job: BackgroundJob) -> dict:
    """
    Send a single campaign message to a recipient.
    Payload: {"campaign_message_id": int}
    """
    msg_id = job.payload.get("campaign_message_id")
    if not msg_id:
        return {"success": False, "error": "missing campaign_message_id"}

    result = await db.execute(
        select(CampaignMessage, CampaignRecipient, Campaign)
        .join(CampaignRecipient, CampaignMessage.recipient_id == CampaignRecipient.id)
        .join(Campaign, CampaignMessage.campaign_id == Campaign.id)
        .where(CampaignMessage.id == msg_id)
    )
    row = result.first()
    if not row:
        return {"success": False, "error": "campaign message not found"}

    cm, recipient, campaign = row

    if cm.status == "sent":
        return {"success": True, "skipped": True, "reason": "already sent"}

    # Find seller channel
    channel_result = await db.execute(
        select(Channel)
        .where(Channel.seller_id == campaign.seller_id)
        .where(Channel.type == "whatsapp")
        .where(Channel.status == "active")
        .limit(1)
    )
    channel = channel_result.scalar_one_or_none()

    if not channel:
        cm.status = "failed"
        cm.error_message = "No active WhatsApp channel"
        recipient.status = "failed"
        await db.commit()
        return {"success": False, "error": "no channel"}

    config = decrypt_config(channel.config_encrypted)
    provider = WhatsAppCloudProvider(
        access_token=config.get("access_token", ""),
        phone_number_id=config.get("phone_number_id", channel.external_id),
        app_secret=config.get("app_secret", ""),
    )

    try:
        send_result = await provider.send_message(recipient.phone, cm.content)
        if send_result.success:
            cm.status = "sent"
            cm.provider_message_id = send_result.provider_message_id
            cm.sent_at = datetime.now(timezone.utc)
            recipient.status = "sent"
        else:
            cm.status = "failed"
            cm.error_message = send_result.error_message
            recipient.status = "failed"
    except Exception as e:
        cm.status = "failed"
        cm.error_message = str(e)
        recipient.status = "failed"

    await db.commit()

    # Recompute campaign status
    all_msgs_result = await db.execute(
        select(CampaignMessage).where(CampaignMessage.campaign_id == campaign.id)
    )
    all_msgs = all_msgs_result.scalars().all()
    statuses = {m.status for m in all_msgs}

    if statuses == {"sent"}:
        campaign.status = "sent"
    elif "queued" not in statuses and "failed" in statuses:
        campaign.status = "partial_failed" if "sent" in statuses else "failed"
    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {"success": cm.status == "sent", "campaign_message_id": msg_id}


# ════════════════════════════════════════════════
# Handler: workflow_run
# ════════════════════════════════════════════════

async def handle_workflow_run(db: AsyncSession, job: BackgroundJob) -> dict:
    """
    Execute a workflow automation run.
    Payload: {"run_id": int}
    """
    from services.workflow_runner import execute_workflow_run

    run_id = job.payload.get("run_id")
    if not run_id:
        return {"success": False, "error": "missing run_id"}

    try:
        result = await execute_workflow_run(db, run_id)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


# ════════════════════════════════════════════════
# Handler: payment_recovery_dispatch (P4.2)
# ════════════════════════════════════════════════

async def handle_payment_recovery_dispatch(db: AsyncSession, job: BackgroundJob) -> dict:
    """Dispatch approved payment recovery reminder with revalidation."""
    from services.payment_recovery.dispatch import handle_payment_recovery_dispatch as dispatch_handler

    return await dispatch_handler(db, job)


# ════════════════════════════════════════════════
# Handler: payment_reconciliation (P1.4/P4.2)
# ════════════════════════════════════════════════

async def handle_payment_reconciliation(db: AsyncSession, job: BackgroundJob) -> dict:
    """Apply a provider status only for the exact current payment attempt."""
    order_id = job.payload.get("order_id")
    if not order_id:
        return {"success": False, "error": "missing order_id", "permanent": True}

    from decimal import Decimal, InvalidOperation
    from datetime import datetime, timezone
    from sqlalchemy import select
    from models.order import Order, OrderStatus
    from models.payment_recovery import PaymentAttempt
    from services.payments.base import PaymentStatus
    from services.payments.factory import (
        _adjust_order_stock_for_payment,
        _get_late_paid_consumed_quantities,
        get_payment_gateway,
    )

    try:
        result = await db.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        if not order:
            return {"success": False, "error": "order not found", "permanent": True}
        if not order.payment_provider or not order.payment_invoice_id:
            return {"success": False, "error": "no payment", "permanent": True}

        provider = order.payment_provider
        invoice_id = order.payment_invoice_id
        gateway = get_payment_gateway(provider)
        status_result = await gateway.check_status(invoice_id)
        if not getattr(status_result, "verified", True):
            return {"success": False, "error": "payment status could not be verified"}

        attempt_result = await db.execute(
            select(PaymentAttempt).where(
                PaymentAttempt.order_id == order.id,
                PaymentAttempt.seller_id == order.seller_id,
                PaymentAttempt.provider == provider,
                PaymentAttempt.external_attempt_id == invoice_id,
                PaymentAttempt.is_current.is_(True),
            )
        )
        payment_attempt = attempt_result.scalar_one_or_none()
        if not payment_attempt:
            return {
                "success": False,
                "error": "current payment attempt not found",
                "permanent": True,
            }

        observed_amount = None
        if status_result.status in (PaymentStatus.PAID, PaymentStatus.REFUNDED):
            try:
                observed_amount = Decimal(str(status_result.amount))
            except (InvalidOperation, TypeError, ValueError):
                return {"success": False, "error": "payment amount could not be verified"}
            if observed_amount != payment_attempt.amount:
                return {"success": False, "error": "payment attempt amount mismatch"}

        locked_result = await db.execute(
            select(Order)
            .where(Order.id == order_id, Order.seller_id == payment_attempt.seller_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        order = locked_result.scalar_one_or_none()
        if not order:
            return {"success": False, "error": "order not found", "permanent": True}
        await db.refresh(payment_attempt)
        if not payment_attempt.is_current:
            return {"success": False, "error": "stale payment attempt", "permanent": True}
        if order.payment_provider != provider or order.payment_invoice_id != invoice_id:
            return {"success": False, "error": "payment identity changed", "permanent": True}

        old_status = order.status.value if hasattr(order.status, "value") else str(order.status)
        new_status = old_status
        paid_lineage = {"paid", "processing", "shipped", "delivered", "done"}
        restore_stock = False
        consume_restored_stock = False

        if old_status == "refunded":
            new_status = old_status
        elif old_status in paid_lineage and status_result.status in (
            PaymentStatus.PENDING,
            PaymentStatus.EXPIRED,
            PaymentStatus.FAILED,
            PaymentStatus.CANCELLED,
        ):
            new_status = old_status
        elif status_result.status == PaymentStatus.PAID:
            if old_status not in paid_lineage:
                consume_restored_stock = old_status == "cancelled"
                order.status = OrderStatus.PAID
                order.paid_at = datetime.now(timezone.utc)
                new_status = "paid"
        elif status_result.status in (PaymentStatus.EXPIRED, PaymentStatus.CANCELLED):
            if old_status not in paid_lineage and old_status != "cancelled":
                order.status = OrderStatus.CANCELLED
                new_status = "cancelled"
                restore_stock = True
        elif status_result.status == PaymentStatus.REFUNDED:
            if old_status in paid_lineage or old_status == "cancelled":
                order.status = OrderStatus.REFUNDED
                new_status = "refunded"
                restore_stock = old_status in paid_lineage

        stock_shortage_product_ids: list[int] = []
        late_paid_consumed_quantities: dict[int, int] = {}
        if restore_stock:
            consumed_quantities = await _get_late_paid_consumed_quantities(db, order.id)
            await _adjust_order_stock_for_payment(
                db,
                order,
                restore=True,
                quantities_by_product=consumed_quantities,
            )
        elif consume_restored_stock:
            stock_shortage_product_ids = await _adjust_order_stock_for_payment(
                db,
                order,
                restore=False,
                consumed_quantities=late_paid_consumed_quantities,
            )
            if stock_shortage_product_ids:
                shortage_ids = ",".join(
                    str(product_id) for product_id in stock_shortage_product_ids
                )
                shortage_note = (
                    "[Pembayaran terlambat terverifikasi; stok tidak cukup untuk produk: "
                    + shortage_ids
                    + "]"
                )
                order.notes = f"{getattr(order, 'notes', '') or ''} {shortage_note}".strip()
                logger.warning(
                    "Reconciled late payment has insufficient stock",
                    extra={"order_id": order.id, "product_ids": stock_shortage_product_ids},
                )

        late_paid_consumed_marker = ""
        if consume_restored_stock:
            consumed_entries = ",".join(
                f"{product_id}:{quantity}"
                for product_id, quantity in sorted(late_paid_consumed_quantities.items())
            )
            late_paid_consumed_marker = f"; late_paid_consumed={consumed_entries};"

        if new_status != old_status:
            from models.order_status_history import OrderStatusHistory
            from core.audit import record_audit

            db.add(OrderStatusHistory(
                order_id=order.id,
                from_status=old_status,
                to_status=new_status,
                changed_by="reconciliation",
                note=(
                    f"Payment {status_result.status.value} via provider status check"
                    + late_paid_consumed_marker
                ),
            ))
            await record_audit(
                db,
                action="payment.status.changed",
                entity_type="order",
                entity_id=order.id,
                seller_id=order.seller_id,
                actor_type="reconciliation",
                before={"status": old_status},
                after={"status": new_status},
                metadata={
                    "provider": provider,
                    "invoice_id": invoice_id,
                    "stock_shortage_product_ids": stock_shortage_product_ids,
                    "late_paid_consumed_quantities": late_paid_consumed_quantities,
                },
            )

        recovery_outcome = None
        if new_status == "paid":
            from services.payment_recovery.outcomes import on_verified_payment

            recovery_outcome = await on_verified_payment(
                db,
                seller_id=order.seller_id,
                order_id=order.id,
                amount=observed_amount,
                observed_at=order.paid_at or datetime.now(timezone.utc),
                payment_attempt_id=payment_attempt.id,
                provider=provider,
                invoice_id=invoice_id,
                currency="IDR",
            )
        elif new_status == "refunded" and old_status != "refunded":
            from services.payment_recovery.outcomes import record_payment_reversal

            recovery_outcome = await record_payment_reversal(
                db,
                seller_id=order.seller_id,
                order_id=order.id,
                amount=observed_amount,
                observed_at=datetime.now(timezone.utc),
                provider=provider,
                invoice_id=invoice_id,
                currency="IDR",
            )

        if new_status != old_status or recovery_outcome is not None:
            await db.commit()

        return {
            "success": True,
            "order_id": order_id,
            "old_status": old_status,
            "new_status": new_status,
            "recovery_outcome": recovery_outcome,
            "stock_shortage_product_ids": stock_shortage_product_ids,
        }
    except Exception as exc:
        await db.rollback()
        logger.exception("Payment reconciliation failed", extra={"order_id": order_id})
        return {"success": False, "error": str(exc)}

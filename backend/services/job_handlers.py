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

async def handle_pending_payment_followup(db: AsyncSession, job: BackgroundJob) -> dict:
    """
    Process a payment follow-up for a single order.
    Payload: {"order_id": int, "followup_number": int}
    """
    from ai.followup import FOLLOWUP_MESSAGES, mark_followup_sent

    order_id = job.payload.get("order_id")
    if not order_id:
        return {"success": False, "error": "missing order_id"}

    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()

    if not order:
        return {"success": False, "error": "order not found"}

    if order.status != OrderStatus.PENDING:
        return {"success": True, "skipped": True, "reason": "order no longer pending"}

    followup_num = min(order.followup_count, 2)
    message = FOLLOWUP_MESSAGES[followup_num]
    items_text = order.items if isinstance(order.items, str) else str(order.items)
    message += f"\n\n📋 Detail order:\n{items_text}\n💰 Total: Rp {order.total:,.0f}"

    # Try to send via WhatsApp if channel exists for seller
    sent_via = "log"
    if order.customer_phone:
        channel_result = await db.execute(
            select(Channel)
            .where(Channel.seller_id == order.seller_id)
            .where(Channel.type == "whatsapp")
            .where(Channel.status == "active")
            .limit(1)
        )
        channel = channel_result.scalar_one_or_none()
        if channel:
            config = decrypt_config(channel.config_encrypted)
            provider = WhatsAppCloudProvider(
                access_token=config.get("access_token", ""),
                phone_number_id=config.get("phone_number_id", channel.external_id),
                app_secret=config.get("app_secret", ""),
            )
            if provider.access_token and provider.phone_number_id:
                try:
                    send_result = await provider.send_message(order.customer_phone, message)
                    if send_result.success:
                        sent_via = "whatsapp"
                    else:
                        logger.warning(f"WhatsApp followup failed: {send_result.error_message}")
                except Exception as e:
                    logger.warning(f"WhatsApp followup error: {e}")

    if sent_via == "log":
        logger.info(
            f"Follow-up #{order.followup_count + 1} → {order.customer_name} (logged, no channel)",
            extra={"order_id": order.id, "seller_id": order.seller_id},
        )

    await mark_followup_sent(order.id, db)
    return {"success": True, "order_id": order.id, "sent_via": sent_via}


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

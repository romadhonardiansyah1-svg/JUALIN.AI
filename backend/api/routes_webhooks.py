"""
JUALIN.AI — Webhook Handlers
Receives payment notifications from Midtrans and Cashi.id.

SECURITY:
- Midtrans: Validates SHA512 signature (order_id + status_code + gross_amount + server_key)
- Cashi.id: Validates x-api-key header + double-checks status via API

Endpoints:
    POST /api/webhooks/midtrans   → Midtrans payment notification
    POST /api/webhooks/cashi      → Cashi.id payment notification

NOTE: These are PUBLIC endpoints (no auth) — they are called by payment providers.
      Security is handled by signature/key validation inside each gateway.
"""
from datetime import datetime, timezone
import json
from fastapi import APIRouter, Request, Response, Query
from sqlalchemy import select

from config import get_settings
from models.database import async_session
from models.inbox import Channel, ChannelContact, InboxThread, InboxMessage
from core.logging_config import get_logger
from core.idempotency import get_or_create_webhook_event, mark_webhook_processed, enqueue_job_record
from services.messaging.whatsapp_cloud import WhatsAppCloudProvider
from services.customer_resolver import resolve_customer, record_customer_event

router = APIRouter()
logger = get_logger(__name__)
settings = get_settings()


@router.post("/midtrans")
async def midtrans_webhook(request: Request):
    """
    Midtrans payment notification webhook.
    
    Midtrans sends a POST with JSON body containing:
    - order_id, status_code, gross_amount, signature_key
    - transaction_status, fraud_status, payment_type
    
    We MUST return 200 OK quickly, otherwise Midtrans will retry.
    """
    try:
        payload = await request.json()
    except Exception:
        logger.warning("Midtrans webhook: invalid JSON body")
        return Response(status_code=400, content="Invalid JSON")

    order_id = payload.get("order_id", "unknown")
    logger.info(
        f"Midtrans webhook received: {order_id}",
        extra={
            "transaction_status": payload.get("transaction_status"),
            "payment_type": payload.get("payment_type"),
        },
    )

    try:
        from services.payments.factory import process_webhook

        async with async_session() as db:
            result = await process_webhook(
                provider="midtrans",
                payload=payload,
                headers=dict(request.headers),
                db=db,
            )

            if result["success"]:
                logger.info(
                    f"Midtrans webhook processed: order #{result['order_id']} → {result['new_status']}",
                )
            else:
                logger.warning(
                    f"Midtrans webhook failed: {result.get('error')}",
                    extra={"order_id": order_id},
                )

    except Exception as e:
        logger.error(f"Midtrans webhook error: {e}", exc_info=True)

    # Always return 200 to prevent retries
    return Response(status_code=200, content="OK")


@router.get("/whatsapp/cloud")
async def whatsapp_cloud_verify(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    """WhatsApp Cloud webhook verification endpoint."""
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        return Response(status_code=200, content=hub_challenge)
    return Response(status_code=403, content="Forbidden")


@router.post("/whatsapp/cloud")
async def whatsapp_cloud_webhook(request: Request):
    """WhatsApp Cloud inbound webhook. Idempotent per message/event."""
    if not settings.ENABLE_WHATSAPP:
        return Response(status_code=200, content="WhatsApp disabled")

    raw_body = await request.body()
    headers = dict(request.headers)
    provider = WhatsAppCloudProvider(app_secret=settings.WHATSAPP_APP_SECRET)
    if not provider.verify_webhook(raw_body, headers):
        logger.warning("WhatsApp webhook: invalid signature")
        return Response(status_code=403, content="Invalid signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        logger.warning("WhatsApp webhook: invalid JSON body")
        return Response(status_code=400, content="Invalid JSON")

    messages = provider.parse_webhook(payload, headers)
    if not messages:
        return Response(status_code=200, content="OK")

    async with async_session() as db:
        for msg in messages:
            event, is_new = await get_or_create_webhook_event(
                db,
                provider="whatsapp_cloud",
                payload=payload,
                event_type="message",
                external_event_id=msg.external_message_id,
            )
            if not is_new or event.status == "processed":
                continue

            channel_result = await db.execute(
                select(Channel)
                .where(Channel.type == "whatsapp")
                .where(Channel.provider == "whatsapp_cloud")
                .where(Channel.external_id == msg.channel_external_id)
                .where(Channel.status == "active")
            )
            channel = channel_result.scalar_one_or_none()
            if not channel:
                await mark_webhook_processed(event, status="ignored", error="No active channel for phone_number_id")
                continue

            contact_result = await db.execute(
                select(ChannelContact)
                .where(ChannelContact.seller_id == channel.seller_id)
                .where(ChannelContact.channel_id == channel.id)
                .where(ChannelContact.external_id == msg.contact_external_id)
            )
            contact = contact_result.scalar_one_or_none()
            if not contact:
                contact = ChannelContact(
                    seller_id=channel.seller_id,
                    channel_id=channel.id,
                    external_id=msg.contact_external_id,
                    phone=msg.phone,
                    name=msg.name,
                    last_seen_at=datetime.now(timezone.utc),
                )
                db.add(contact)
                await db.flush()
            else:
                contact.name = msg.name or contact.name
                contact.phone = msg.phone or contact.phone
                contact.last_seen_at = datetime.now(timezone.utc)

            thread_result = await db.execute(
                select(InboxThread)
                .where(InboxThread.seller_id == channel.seller_id)
                .where(InboxThread.channel_id == channel.id)
                .where(InboxThread.contact_id == contact.id)
            )
            thread = thread_result.scalar_one_or_none()
            if not thread:
                thread = InboxThread(
                    seller_id=channel.seller_id,
                    channel_id=channel.id,
                    contact_id=contact.id,
                    external_thread_id=msg.contact_external_id,
                )
                db.add(thread)
                await db.flush()

            customer, _ = await resolve_customer(
                db,
                seller_id=channel.seller_id,
                phone=contact.phone or msg.phone,
                whatsapp_id=contact.external_id,
                session_id=f"wa:{contact.external_id}",
                name=contact.name or msg.name,
            )

            existing_msg = await db.execute(
                select(InboxMessage).where(InboxMessage.external_message_id == msg.external_message_id)
            )
            if not existing_msg.scalar_one_or_none():
                db.add(InboxMessage(
                    seller_id=channel.seller_id,
                    thread_id=thread.id,
                    direction="inbound",
                    role="customer",
                    content_type=msg.content_type,
                    content=msg.content,
                    external_message_id=msg.external_message_id,
                    raw_payload=msg.raw,
                ))
                thread.last_message_preview = msg.content[:500]
                thread.last_message_at = datetime.now(timezone.utc)
                thread.unread_count = (thread.unread_count or 0) + 1
                await record_customer_event(
                    db,
                    seller_id=channel.seller_id,
                    customer_id=customer.id,
                    event_type="chat.inbound",
                    title="Pesan WhatsApp masuk",
                    data={"thread_id": thread.id, "message_id": msg.external_message_id, "content": msg.content[:500]},
                    source="whatsapp_cloud",
                )

            if thread.mode == "ai":
                await enqueue_job_record(
                    db,
                    job_type="inbox_ai_reply",
                    seller_id=channel.seller_id,
                    payload={"thread_id": thread.id, "message_id": msg.external_message_id},
                    idempotency_key=f"inbox_ai_reply:{msg.external_message_id}",
                )

            await mark_webhook_processed(event)
        await db.commit()

    return Response(status_code=200, content="OK")


@router.post("/cashi")
async def cashi_webhook(request: Request):
    """
    Cashi.id payment notification webhook.
    
    Cashi.id sends a POST with JSON body containing:
    - order_id, status, amount
    - Headers include x-api-key for authentication
    
    We MUST return 200 OK quickly.
    """
    try:
        payload = await request.json()
    except Exception:
        logger.warning("Cashi webhook: invalid JSON body")
        return Response(status_code=400, content="Invalid JSON")

    order_id = payload.get("order_id", "unknown")
    logger.info(
        f"Cashi webhook received: {order_id}",
        extra={
            "status": payload.get("status"),
            "amount": payload.get("amount"),
        },
    )

    try:
        from services.payments.factory import process_webhook

        async with async_session() as db:
            result = await process_webhook(
                provider="cashi",
                payload=payload,
                headers=dict(request.headers),
                db=db,
            )

            if result["success"]:
                logger.info(
                    f"Cashi webhook processed: order #{result['order_id']} → {result['new_status']}",
                )
            else:
                logger.warning(
                    f"Cashi webhook failed: {result.get('error')}",
                    extra={"order_id": order_id},
                )

    except Exception as e:
        logger.error(f"Cashi webhook error: {e}", exc_info=True)

    # Always return 200 to prevent retries
    return Response(status_code=200, content="OK")

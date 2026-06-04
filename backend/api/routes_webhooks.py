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
from fastapi import APIRouter, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import async_session
from core.logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


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

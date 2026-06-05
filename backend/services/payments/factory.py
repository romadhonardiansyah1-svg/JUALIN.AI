"""
JUALIN.AI — Payment Gateway Factory
Creates the appropriate gateway instance based on provider name.

Usage:
    from services.payments.factory import get_payment_gateway, create_payment_for_order
    
    # Get gateway directly:
    gateway = get_payment_gateway("midtrans")
    result = await gateway.create_payment(...)
    
    # Or use the high-level helper:
    result = await create_payment_for_order(order, method="qris", provider="cashi", db=db)
"""
from datetime import datetime, timezone
import secrets
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from core.logging_config import get_logger
from core.exceptions import PaymentError
from services.payments.base import PaymentGateway, PaymentStatus

settings = get_settings()
logger = get_logger(__name__)

# Singleton instances (created once, reused)
_gateways: dict[str, PaymentGateway] = {}


def get_payment_gateway(provider: str = None) -> PaymentGateway:
    """
    Get a payment gateway instance by provider name.
    Creates singleton instances on first call.
    
    Args:
        provider: "midtrans" or "cashi" (default from config)
    
    Returns:
        PaymentGateway instance
    
    Raises:
        PaymentError if provider is invalid or not configured
    """
    provider = provider or settings.DEFAULT_PAYMENT_PROVIDER

    if provider in _gateways:
        return _gateways[provider]

    if provider == "midtrans":
        if not settings.MIDTRANS_SERVER_KEY:
            raise PaymentError(
                message="Midtrans belum dikonfigurasi. Set MIDTRANS_SERVER_KEY di .env",
                provider="midtrans",
            )
        from services.payments.midtrans_gateway import MidtransGateway
        _gateways["midtrans"] = MidtransGateway()
        return _gateways["midtrans"]

    elif provider == "cashi":
        if not settings.CASHI_API_KEY:
            raise PaymentError(
                message="Cashi.id belum dikonfigurasi. Set CASHI_API_KEY di .env",
                provider="cashi",
            )
        from services.payments.cashi_gateway import CashiGateway
        _gateways["cashi"] = CashiGateway()
        return _gateways["cashi"]

    else:
        raise PaymentError(
            message=f"Provider '{provider}' tidak dikenali. Gunakan 'midtrans' atau 'cashi'.",
            provider=provider,
        )


async def create_payment_for_order(
    order,
    method: str = "qris",
    provider: str = None,
    db: AsyncSession = None,
) -> dict:
    """
    High-level helper: create a payment for an existing Order object.
    Updates the Order with payment info and returns a response dict.
    
    Args:
        order: Order model instance
        method: Payment method ("qris", "snap", "va_bca", etc.)
        provider: "midtrans" or "cashi" (auto-detected if not specified)
        db: AsyncSession for saving order updates
    
    Returns:
        dict with payment info for the frontend
    """
    # Auto-detect provider based on method if not specified
    if not provider:
        if method == "snap":
            provider = "midtrans"
        else:
            provider = settings.DEFAULT_PAYMENT_PROVIDER

    gateway = get_payment_gateway(provider)
    if not order.payment_access_token:
        order.payment_access_token = secrets.token_urlsafe(32)

    # Create payment via gateway
    result = await gateway.create_payment(
        order_id=order.id,
        amount=int(order.total),
        customer_name=order.customer_name,
        customer_email="",  # Not collected in chat flow
        customer_phone=order.customer_phone or "",
        items=order.items if isinstance(order.items, list) else [],
        method=method,
        payment_token=order.payment_access_token,
    )

    if not result.success:
        logger.error(
            f"Payment creation failed for order #{order.id}",
            extra={
                "provider": provider,
                "method": method,
                "error": result.error_message,
            },
        )
        raise PaymentError(
            message=result.error_message or "Gagal membuat pembayaran",
            provider=provider,
        )

    # Update order with payment info
    if db:
        order.payment_method = result.method
        order.payment_provider = result.provider
        order.payment_invoice_id = result.order_id
        order.payment_url = result.payment_url or result.qr_data
        order.payment_qr_data = result.qr_data
        order.payment_va_number = result.token if result.method.startswith("va_") else None
        order.payment_expires_at = result.expires_at

        # Record status change
        from models.order_status_history import OrderStatusHistory
        history = OrderStatusHistory(
            order_id=order.id,
            from_status=order.status.value if hasattr(order.status, 'value') else str(order.status),
            to_status="pending",
            changed_by="payment_system",
            note=f"Payment created via {provider} ({method})",
        )
        db.add(history)
        await db.commit()

    return {
        "success": True,
        "order_id": order.id,
        "status": order.status.value if hasattr(order.status, "value") else str(order.status),
        "invoice_id": result.order_id,
        "provider": result.provider,
        "method": result.method,
        "amount": result.amount,
        "payment_url": result.payment_url,
        "qr_data": result.qr_data,
        "snap_token": result.token,       # For Midtrans Snap.js
        "va_number": result.token if method.startswith("va_") else None,
        "expires_at": result.expires_at,
        "payment_created": True,
        "public_token": order.payment_access_token,
    }


async def process_webhook(
    provider: str,
    payload: dict,
    headers: dict,
    db: AsyncSession,
) -> dict:
    """
    Process a webhook callback from a payment provider.
    Validates the webhook, updates order status, and records history.
    
    Returns:
        dict with processing result
    """
    from models.order import Order, OrderStatus
    from models.order_status_history import OrderStatusHistory
    from sqlalchemy import select

    gateway = get_payment_gateway(provider)
    result = await gateway.validate_webhook(payload, headers)

    if not result.valid:
        logger.warning(
            f"Invalid {provider} webhook",
            extra={"error": result.error_message},
        )
        return {"success": False, "error": result.error_message}

    # Extract our internal order ID from the invoice ID
    # Format: JUALIN-{order_id} or JUALIN-{order_id}-{timestamp}
    invoice_id = result.order_id or ""
    try:
        parts = invoice_id.replace("JUALIN-", "").split("-")
        internal_order_id = int(parts[0])
    except (ValueError, IndexError):
        logger.error(f"Cannot parse order ID from invoice: {invoice_id}")
        return {"success": False, "error": f"Invalid invoice ID: {invoice_id}"}

    # Find order
    order_result = await db.execute(
        select(Order).where(Order.id == internal_order_id)
    )
    order = order_result.scalar_one_or_none()

    if not order:
        logger.error(f"Webhook: order #{internal_order_id} not found")
        return {"success": False, "error": f"Order #{internal_order_id} not found"}

    # Map payment status to order status
    old_status = order.status.value if hasattr(order.status, 'value') else str(order.status)

    restore_stock = False
    terminal_paid_statuses = {"paid", "shipped", "done"}

    if old_status in terminal_paid_statuses and result.status in (
        PaymentStatus.PENDING,
        PaymentStatus.EXPIRED,
        PaymentStatus.FAILED,
        PaymentStatus.CANCELLED,
    ):
        new_status = old_status
    elif result.status == PaymentStatus.PAID:
        order.status = OrderStatus.PAID
        order.paid_at = datetime.now(timezone.utc)
        new_status = "paid"
    elif result.status == PaymentStatus.EXPIRED:
        order.status = OrderStatus.CANCELLED
        new_status = "cancelled"
        restore_stock = True
    elif result.status == PaymentStatus.FAILED:
        new_status = old_status  # Don't change status on failed
    elif result.status == PaymentStatus.CANCELLED:
        order.status = OrderStatus.CANCELLED
        new_status = "cancelled"
        restore_stock = True
    elif result.status == PaymentStatus.REFUNDED:
        order.status = OrderStatus.REFUNDED
        new_status = "refunded"
        restore_stock = True
    else:
        new_status = old_status  # Pending — no change

    if restore_stock and old_status not in ("cancelled", "refunded"):
        from models.product import Product
        items = order.items if isinstance(order.items, list) else []
        for item in items:
            product_id = item.get("product_id")
            if not product_id:
                continue
            product_result = await db.execute(
                select(Product).where(
                    Product.id == product_id,
                    Product.seller_id == order.seller_id,
                )
            )
            product = product_result.scalar_one_or_none()
            if product:
                product.stok += item.get("qty", 1)

    # Only record history if status actually changed
    if new_status != old_status:
        history = OrderStatusHistory(
            order_id=order.id,
            from_status=old_status,
            to_status=new_status,
            changed_by=f"webhook_{provider}",
            note=f"Payment {result.status.value} via {provider}",
        )
        db.add(history)
        from core.audit import record_audit
        await record_audit(
            db,
            action="payment.status.changed",
            entity_type="order",
            entity_id=order.id,
            seller_id=order.seller_id,
            actor_type="webhook",
            before={"status": old_status},
            after={"status": new_status},
            metadata={"provider": provider, "invoice_id": invoice_id, "amount": result.amount},
        )

    await db.commit()

    logger.info(
        f"Webhook processed: order #{internal_order_id} → {new_status}",
        extra={
            "order_id": internal_order_id,
            "provider": provider,
            "old_status": old_status,
            "new_status": new_status,
            "amount": result.amount,
        },
    )

    return {
        "success": True,
        "order_id": internal_order_id,
        "old_status": old_status,
        "new_status": new_status,
        "provider": provider,
    }

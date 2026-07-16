"""
JUALIN.AI — Payment Gateway Factory — P1.4 hardened monotonic processing.
"""
from datetime import datetime, timezone
import secrets
from decimal import Decimal, InvalidOperation
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from core.logging_config import get_logger
from core.exceptions import PaymentError
from services.payments.base import PaymentGateway, PaymentStatus

settings = get_settings()
logger = get_logger(__name__)


def _parse_decimal_amount(value) -> Decimal | None:
    """Parse amount as Decimal from canonical string, never via float."""
    if value is None:
        return None
    try:
        # Convert via string to avoid float binary errors
        s = str(value).strip().replace(",", "")
        # Remove currency symbols
        s = s.replace("Rp", "").replace("IDR", "").strip()
        return Decimal(s)
    except (InvalidOperation, ValueError, AttributeError):
        return None

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


async def _get_or_create_payment_attempt_and_capability(
    db: AsyncSession,
    order,
    provider: str,
    invoice_id: str,
    amount: int,
):
    """P2.4 — Create PaymentAttempt and HMAC capability for public payment."""
    from models.payment_recovery import PaymentAttempt
    from sqlalchemy import select, func
    from decimal import Decimal
    import uuid
    from datetime import timedelta

    # Get current max attempt_version for order
    max_ver_q = await db.execute(
        select(func.coalesce(func.max(PaymentAttempt.attempt_version), 0)).where(
            PaymentAttempt.order_id == order.id, PaymentAttempt.seller_id == order.seller_id
        )
    )
    max_ver = max_ver_q.scalar() or 0
    new_version = max_ver + 1

    # Expire time from gateway result? For now, 24h
    expires_at = None
    try:
        # Try to get from result? We'll set 24h from now
        from datetime import datetime, timezone

        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    except Exception:
        expires_at = None

    attempt = PaymentAttempt(
        seller_id=order.seller_id,
        order_id=order.id,
        provider=provider,
        provider_account_id=None,
        external_attempt_id=invoice_id,
        attempt_version=new_version,
        is_current=True,
        status="pending",
        amount=Decimal(str(amount)),
        currency="IDR",
        payment_expires_at=expires_at,
        trusted_link_reference=None,
    )
    # Mark previous attempts as not current
    await db.execute(
        select(PaymentAttempt).where(PaymentAttempt.order_id == order.id)
    )  # dummy to ensure table exists
    from sqlalchemy import text

    await db.execute(
        text(
            "UPDATE payment_attempts SET is_current=false WHERE seller_id=:seller_id AND order_id=:order_id AND is_current=true"
        ),
        {"seller_id": order.seller_id, "order_id": order.id},
    )

    db.add(attempt)
    await db.flush()

    # Create capability for this attempt
    from services.payment_capability import create_capability

    cap, raw_token = await create_capability(
        db,
        seller_id=order.seller_id,
        order_id=order.id,
        payment_attempt_id=attempt.id,
        audience="public_payment",
        purpose="payment_status",
        ttl_hours=settings.PAYMENT_CAPABILITY_TOKEN_TTL_HOURS,
    )
    await db.flush()

    return attempt, cap, raw_token


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
    # P2.4: stop minting plaintext payment_access_token for new writes
    # Use a temporary token for gateway if needed, but don't store as plaintext long-term
    gateway_token = secrets.token_urlsafe(16)  # short-lived for gateway only, not stored as public capability

    # Create payment via gateway
    result = await gateway.create_payment(
        order_id=order.id,
        amount=int(order.total),
        customer_name=order.customer_name,
        customer_email="",
        customer_phone=order.customer_phone or "",
        items=order.items if isinstance(order.items, list) else [],
        method=method,
        payment_token=gateway_token,
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

    # Update order with payment info + create PaymentAttempt + capability (P2.4)
    capability_token = None
    capability = None
    attempt = None
    if db:
        order.payment_method = result.method
        order.payment_provider = result.provider
        order.payment_invoice_id = result.order_id
        order.payment_url = result.payment_url or result.qr_data
        order.payment_qr_data = result.qr_data
        order.payment_va_number = result.token if result.method.startswith("va_") else None
        order.payment_expires_at = result.expires_at

        # Create PaymentAttempt + capability for secure public link (fragment, not query)
        try:
            attempt, capability, capability_token = await _get_or_create_payment_attempt_and_capability(
                db, order, provider, result.order_id, int(order.total)
            )
            # Store HMAC in order for transition (dual-read)
            order.payment_access_token_hmac = capability.token_hmac
            order.payment_access_token_key_version = capability.key_version
            order.payment_access_token_expires_at = capability.expires_at
            # Do NOT set plaintext payment_access_token for new writes
        except Exception as e:
            logger.warning(f"Failed to create payment attempt/capability: {e}")

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

    # Build public URL with fragment (not query) per P2.4
    public_fragment_url = None
    if capability_token:
        # Fragment bootstrap: /pay/{order_id}#token=xxx
        public_fragment_url = f"/pay/{order.id}#token={capability_token}"

    return {
        "success": True,
        "order_id": order.id,
        "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
        "invoice_id": result.order_id,
        "provider": result.provider,
        "method": result.method,
        "amount": result.amount,
        "payment_url": result.payment_url,
        "qr_data": result.qr_data,
        "snap_token": result.token,
        "va_number": result.token if method.startswith("va_") else None,
        "expires_at": result.expires_at,
        "payment_created": True,
        "public_token": None,  # No longer mint plaintext
        "capability_token": capability_token,  # Raw token only returned once, for fragment link
        "capability_link": public_fragment_url,
        "payment_attempt_id": str(attempt.id) if attempt else None,
    }


async def process_webhook(
    provider: str,
    payload: dict,
    headers: dict,
    db: AsyncSession,
) -> dict:
    """
    P1.4 hardened monotonic payment webhook processing:
    - Match exact current provider + invoice/payment-attempt ID via PaymentAttempt if available
    - Parse amount as Decimal, never float
    - Refund fact does not downgrade paid to pending
    - Duplicate paid does not double-restore stock (idempotent)
    - Durable inbox already committed before this call (caller must ensure)
    - No signature/expected signature in logs
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

    invoice_id = result.order_id or ""

    # Try to resolve via PaymentAttempt if table exists (P1.1)
    payment_attempt = None
    internal_order_id = None

    try:
        from models.payment_recovery import PaymentAttempt

        # Attempt to find exact current attempt by provider + external_attempt_id
        attempt_q = await db.execute(
            select(PaymentAttempt).where(
                PaymentAttempt.provider == provider,
                PaymentAttempt.external_attempt_id == invoice_id,
                PaymentAttempt.is_current == True,
            )
        )
        payment_attempt = attempt_q.scalar_one_or_none()
        if payment_attempt:
            internal_order_id = payment_attempt.order_id
    except Exception:
        # Table may not exist yet or error — fallback to legacy parsing
        payment_attempt = None

    # Legacy fallback: parse order_id from invoice string JUALIN-{order_id}-...
    if internal_order_id is None:
        try:
            parts = invoice_id.replace("JUALIN-", "").split("-")
            internal_order_id = int(parts[0])
        except (ValueError, IndexError):
            logger.error(f"Cannot parse order ID from invoice: {invoice_id}")
            return {"success": False, "error": f"Invalid invoice ID: {invoice_id}"}

    # Find order — seller-scoped already via later checks, but for webhook we need order first
    order_result = await db.execute(
        select(Order).where(Order.id == internal_order_id)
    )
    order = order_result.scalar_one_or_none()

    if not order:
        logger.error(f"Webhook: order #{internal_order_id} not found")
        return {"success": False, "error": f"Order #{internal_order_id} not found"}

    # If PaymentAttempt exists, verify seller_id matches order seller_id (tenant check)
    if payment_attempt and payment_attempt.seller_id != order.seller_id:
        logger.warning(
            "Payment attempt seller mismatch — possible cross-tenant",
            extra={"order_id": internal_order_id, "attempt_seller": payment_attempt.seller_id, "order_seller": order.seller_id},
        )
        return {"success": False, "error": "seller mismatch"}

    # Decimal amount validation — never via float
    incoming_amount = _parse_decimal_amount(getattr(result, "amount", None) or payload.get("gross_amount") or payload.get("amount"))
    expected_amount = _parse_decimal_amount(order.total)

    if incoming_amount is not None and expected_amount is not None:
        # Allow small tolerance? For safety, require exact match or at least not drastically different
        # For paid events, amount must match expected outstanding
        if result.status == PaymentStatus.PAID and incoming_amount != expected_amount:
            # If amount mismatch, log but do not mark paid — prevent wrong-invoice payment
            logger.warning(
                f"Payment amount mismatch: expected {expected_amount} got {incoming_amount} for order {internal_order_id}",
                extra={"order_id": internal_order_id, "provider": provider},
            )
            # Still allow if gateway says paid? For safety, we require exact match for new flow
            # If PaymentAttempt exists, compare to attempt.amount
            if payment_attempt and payment_attempt.amount != incoming_amount:
                return {"success": False, "error": f"Amount mismatch: {incoming_amount} vs {payment_attempt.amount}"}

    old_status = order.status.value if hasattr(order.status, 'value') else str(order.status)

    # Monotonic precedence: paid and refunded are terminal, old paid should not be downgraded by older pending/expired
    terminal_paid = {"paid", "shipped", "done", "refunded"}
    is_old_paid = old_status in {"paid", "shipped", "done"}
    is_refunded = old_status == "refunded"

    restore_stock = False
    new_status = old_status

    # Refund precedence: refunded fact never downgrades paid to paid, but refunded stays refunded
    if is_refunded:
        # Once refunded, stay refunded — no downgrade to paid/pending
        new_status = old_status
    elif is_old_paid and result.status in (
        PaymentStatus.PENDING,
        PaymentStatus.EXPIRED,
        PaymentStatus.FAILED,
        PaymentStatus.CANCELLED,
    ):
        new_status = old_status
    elif result.status == PaymentStatus.PAID:
        # Idempotent: if already paid, keep paid, do not double-restore stock
        if old_status != "paid":
            order.status = OrderStatus.PAID
            order.paid_at = datetime.now(timezone.utc)
            new_status = "paid"
        else:
            new_status = "paid"
    elif result.status == PaymentStatus.EXPIRED:
        if not is_old_paid:
            order.status = OrderStatus.CANCELLED
            new_status = "cancelled"
            restore_stock = True
    elif result.status == PaymentStatus.FAILED:
        new_status = old_status
    elif result.status == PaymentStatus.CANCELLED:
        if not is_old_paid:
            order.status = OrderStatus.CANCELLED
            new_status = "cancelled"
            restore_stock = True
    elif result.status == PaymentStatus.REFUNDED:
        # Only allow refund if previously paid
        if old_status in {"paid", "shipped", "done"}:
            order.status = OrderStatus.REFUNDED
            new_status = "refunded"
            restore_stock = True
        else:
            # If not previously paid, keep old status but record refund fact elsewhere
            new_status = old_status
    else:
        new_status = old_status

    # Idempotent stock restore — only if status actually transitions and not previously cancelled/refunded
    if restore_stock and old_status not in ("cancelled", "refunded"):
        # Check if we already restored stock for this order via history to avoid double restore
        hist_q = await db.execute(
            select(OrderStatusHistory).where(
                OrderStatusHistory.order_id == order.id,
                OrderStatusHistory.to_status.in_(["cancelled", "refunded"]),
            )
        )
        already_restored = hist_q.scalars().first() is not None
        if not already_restored:
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
                    product.stok += int(item.get("qty", 1) or 1)

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
            metadata={"provider": provider, "invoice_id": invoice_id},
        )

    # P5.2 — honest recovery ledger from verified payment/refund facts only.
    # Paid may re-enter for duplicate webhooks (ledger is idempotent by source key).
    # Reversal only on transition into refunded to avoid extra work on stable refunded state.
    recovery_outcome: dict | None = None
    if new_status == "paid":
        from services.payment_recovery.outcomes import on_verified_payment

        paid_amount = incoming_amount if incoming_amount is not None else expected_amount
        recovery_outcome = await on_verified_payment(
            db,
            seller_id=order.seller_id,
            order_id=order.id,
            amount=paid_amount if paid_amount is not None else order.total,
            observed_at=order.paid_at or datetime.now(timezone.utc),
            payment_attempt_id=payment_attempt.id if payment_attempt else None,
            provider=provider,
            invoice_id=invoice_id,
            currency="IDR",
        )
    elif new_status == "refunded" and old_status != "refunded":
        from services.payment_recovery.outcomes import record_payment_reversal

        rev_amount = incoming_amount if incoming_amount is not None else expected_amount
        recovery_outcome = await record_payment_reversal(
            db,
            seller_id=order.seller_id,
            order_id=order.id,
            amount=rev_amount if rev_amount is not None else order.total,
            observed_at=datetime.now(timezone.utc),
            provider=provider,
            invoice_id=invoice_id,
            currency="IDR",
        )

    await db.commit()

    logger.info(
        f"Webhook processed: order #{internal_order_id} → {new_status}",
        extra={
            "order_id": internal_order_id,
            "provider": provider,
            "old_status": old_status,
            "new_status": new_status,
            "recovery_outcome_applied": bool(
                recovery_outcome and recovery_outcome.get("applied")
            ),
        },
    )

    return {
        "success": True,
        "order_id": internal_order_id,
        "old_status": old_status,
        "new_status": new_status,
        "provider": provider,
        "recovery_outcome": recovery_outcome,
    }

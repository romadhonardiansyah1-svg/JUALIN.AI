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


def get_payment_gateway(provider: str | None = None) -> PaymentGateway:
    """Return the sole supported payment gateway: Midtrans."""
    provider = provider or "midtrans"
    if provider != "midtrans":
        raise PaymentError(
            message="Provider pembayaran tidak lagi didukung. Gunakan Midtrans.",
            provider=provider,
        )

    if provider in _gateways:
        return _gateways[provider]

    if not settings.MIDTRANS_SERVER_KEY:
        raise PaymentError(
            message="Midtrans belum dikonfigurasi. Set MIDTRANS_SERVER_KEY di .env",
            provider="midtrans",
        )

    from services.payments.midtrans_gateway import MidtransGateway

    _gateways["midtrans"] = MidtransGateway()
    return _gateways["midtrans"]


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


async def _lock_order_for_payment(db: AsyncSession, order_id: int):
    """Serialize invoice creation for an order and refresh stale identity-map state."""
    from sqlalchemy import select
    from models.order import Order

    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def _adjust_order_stock_for_payment(
    db: AsyncSession,
    order,
    *,
    restore: bool,
    quantities_by_product: dict[int, int] | None = None,
    consumed_quantities: dict[int, int] | None = None,
) -> list[int]:
    """Adjust seller-scoped stock under locks and track actual consumption."""
    from sqlalchemy import select
    from models.product import Product

    if quantities_by_product is None:
        items = order.items if isinstance(order.items, list) else []
    else:
        items = [
            {"product_id": product_id, "qty": quantity}
            for product_id, quantity in quantities_by_product.items()
        ]

    shortage_product_ids: list[int] = []
    for item in items:
        product_id = item.get("product_id")
        if not product_id:
            continue
        quantity = int(item.get("qty", 1) or 1)
        product_result = await db.execute(
            select(Product).where(
                Product.id == product_id,
                Product.seller_id == order.seller_id,
            ).with_for_update()
        )
        product = product_result.scalar_one_or_none()
        if not product:
            shortage_product_ids.append(product_id)
            continue
        if restore:
            product.stok += quantity
        elif product.stok >= quantity:
            product.stok -= quantity
            if consumed_quantities is not None:
                consumed_quantities[product_id] = (
                    consumed_quantities.get(product_id, 0) + quantity
                )
        else:
            shortage_product_ids.append(product_id)

    return shortage_product_ids


async def _get_late_paid_consumed_quantities(
    db: AsyncSession,
    order_id: int,
) -> dict[int, int] | None:
    """Load immutable stock consumption recorded for the latest late payment."""
    from sqlalchemy import select
    from models.order_status_history import OrderStatusHistory

    marker = "late_paid_consumed="
    result = await db.execute(
        select(OrderStatusHistory.note)
        .where(
            OrderStatusHistory.order_id == order_id,
            OrderStatusHistory.to_status == "paid",
            OrderStatusHistory.note.like(f"%{marker}%"),
        )
        .order_by(OrderStatusHistory.created_at.desc())
        .limit(1)
    )
    note = result.scalar_one_or_none()
    if not isinstance(note, str) or marker not in note:
        return None

    raw_entries = note.rsplit(marker, 1)[1].split(";", 1)[0]
    consumed: dict[int, int] = {}
    for entry in raw_entries.split(","):
        if not entry.strip() or ":" not in entry:
            continue
        raw_product_id, raw_quantity = entry.split(":", 1)
        try:
            product_id = int(raw_product_id.strip())
            quantity = int(raw_quantity.strip())
        except ValueError:
            continue
        if quantity > 0:
            consumed[product_id] = consumed.get(product_id, 0) + quantity
    return consumed


async def create_payment_for_order(
    order,
    method: str = "snap",
    provider: str | None = None,
    db: AsyncSession = None,
) -> dict:
    """Create at most one durable external invoice for an order."""
    if db:
        locked_order = await _lock_order_for_payment(db, order.id)
        if not locked_order:
            raise PaymentError(message="Order tidak ditemukan", provider=provider or "")
        order = locked_order

        from models.order import OrderStatus
        if order.status not in (OrderStatus.PENDING, OrderStatus.CONFIRMED):
            raise PaymentError(
                message="Order tidak dalam status yang dapat dibayar",
                provider=provider or "midtrans",
            )
        if order.payment_provider and order.payment_provider != "midtrans":
            raise PaymentError(
                message=(
                    "Provider pembayaran lama tidak lagi didukung. "
                    "Batalkan order ini dan buat order baru untuk membayar melalui Midtrans."
                ),
                provider=order.payment_provider,
            )
        if order.payment_provider and order.payment_invoice_id:
            capability_token = None
            attempt = None
            repaired_amount = None

            # An external invoice may have been committed before capability setup
            # failed. Repair that partial state without creating another invoice.
            if not getattr(order, "payment_access_token_hmac", None):
                gateway = get_payment_gateway(order.payment_provider)
                status_result = await gateway.check_status(order.payment_invoice_id)
                repaired_amount = _parse_decimal_amount(status_result.amount)
                expected_amount = _parse_decimal_amount(order.total)
                amount_is_valid = (
                    repaired_amount is not None
                    and expected_amount is not None
                    and repaired_amount == repaired_amount.to_integral_value()
                    and repaired_amount == expected_amount
                )
                if not getattr(status_result, "verified", True) or not amount_is_valid:
                    raise PaymentError(
                        message="Invoice ada, tetapi nominalnya tidak dapat diverifikasi dengan aman",
                        provider=order.payment_provider,
                    )
                try:
                    attempt, capability, capability_token = (
                        await _get_or_create_payment_attempt_and_capability(
                            db,
                            order,
                            order.payment_provider,
                            order.payment_invoice_id,
                            int(repaired_amount),
                        )
                    )
                    order.payment_access_token_hmac = capability.token_hmac
                    order.payment_access_token_key_version = capability.key_version
                    order.payment_access_token_expires_at = capability.expires_at
                    await db.commit()
                except PaymentError:
                    await db.rollback()
                    raise
                except Exception:
                    await db.rollback()
                    logger.exception(
                        "Failed to repair payment capability",
                        extra={"order_id": order.id},
                    )
                    raise PaymentError(
                        message="Akses pembayaran belum dapat dipulihkan; coba lagi",
                        provider=order.payment_provider,
                    )

            return {
                "success": True,
                "order_id": order.id,
                "status": order.status.value if hasattr(order.status, "value") else str(order.status),
                "invoice_id": order.payment_invoice_id,
                "provider": order.payment_provider,
                "method": order.payment_method,
                "amount": repaired_amount if repaired_amount is not None else order.total,
                "payment_url": order.payment_url,
                "qr_data": order.payment_qr_data,
                "snap_token": None,
                "va_number": order.payment_va_number,
                "expires_at": order.payment_expires_at,
                "payment_created": True,
                "already_exists": True,
                "public_token": None,
                "capability_token": capability_token,
                "capability_link": (
                    f"/pay/{order.id}#token={capability_token}"
                    if capability_token else None
                ),
                "payment_attempt_id": str(attempt.id) if attempt else None,
            }

    provider = provider or "midtrans"
    if provider != "midtrans" or method != "snap":
        raise PaymentError(
            message="Metode pembayaran yang didukung hanya Midtrans Snap.",
            provider=provider,
        )
    gateway = get_payment_gateway(provider)
    gateway_token = secrets.token_urlsafe(16)
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
            extra={"provider": provider, "method": method, "error": result.error_message},
        )
        raise PaymentError(message=result.error_message or "Gagal membuat pembayaran", provider=provider)

    capability_token = None
    attempt = None
    if db:
        order.payment_method = result.method
        order.payment_provider = result.provider
        order.payment_invoice_id = result.order_id
        order.payment_url = result.payment_url or result.qr_data
        order.payment_qr_data = result.qr_data
        order.payment_va_number = result.token if result.method.startswith("va_") else None
        order.payment_expires_at = result.expires_at

        # Persist the externally-created invoice identity first. If capability
        # setup fails, a retry reloads and reuses this invoice instead of
        # creating another remote charge target.
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception(
                "Failed to persist external payment invoice",
                extra={"order_id": order.id, "provider": result.provider},
            )
            raise PaymentError(
                message="Invoice dibuat tetapi belum dapat dicatat dengan aman; hubungi dukungan",
                provider=result.provider,
            )

        try:
            order = await _lock_order_for_payment(db, order.id)
            attempt, capability, capability_token = await _get_or_create_payment_attempt_and_capability(
                db, order, result.provider, result.order_id, int(result.amount)
            )
            order.payment_access_token_hmac = capability.token_hmac
            order.payment_access_token_key_version = capability.key_version
            order.payment_access_token_expires_at = capability.expires_at

            from models.order_status_history import OrderStatusHistory
            db.add(OrderStatusHistory(
                order_id=order.id,
                from_status=order.status.value if hasattr(order.status, "value") else str(order.status),
                to_status="pending",
                changed_by="payment_system",
                note=f"Payment created via {result.provider} ({method})",
            ))
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception(
                "Failed to persist payment attempt and capability",
                extra={"order_id": order.id},
            )
            raise PaymentError(
                message="Invoice sudah dicatat, tetapi akses pembayaran belum dapat disiapkan; coba lagi",
                provider=result.provider,
            )

    capability_link = f"/pay/{order.id}#token={capability_token}" if capability_token else None
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
        "snap_token": result.token,
        "va_number": result.token if method.startswith("va_") else None,
        "expires_at": result.expires_at,
        "payment_created": True,
        "public_token": None,
        "capability_token": capability_token,
        "capability_link": capability_link,
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

        # Resolve the exact attempt first, including stale attempts so they cannot
        # fall through to legacy order-ID parsing.
        attempt_q = await db.execute(
            select(PaymentAttempt).where(
                PaymentAttempt.provider == provider,
                PaymentAttempt.external_attempt_id == invoice_id,
            )
        )
        payment_attempt = attempt_q.scalar_one_or_none()
        if payment_attempt and not payment_attempt.is_current:
            return {"success": False, "error": "stale payment attempt"}
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
        select(Order)
        .where(Order.id == internal_order_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    order = order_result.scalar_one_or_none()

    if not order:
        logger.error(f"Webhook: order #{internal_order_id} not found")
        return {"success": False, "error": f"Order #{internal_order_id} not found"}

    if (
        order.payment_provider != provider
        or order.payment_invoice_id != invoice_id
    ):
        logger.warning(
            "Webhook payment identity mismatch",
            extra={"order_id": internal_order_id, "provider": provider},
        )
        return {"success": False, "error": "payment identity mismatch"}

    if payment_attempt:
        await db.refresh(payment_attempt)
        if not payment_attempt.is_current:
            return {"success": False, "error": "stale payment attempt"}

    # If PaymentAttempt exists, verify seller_id matches order seller_id (tenant check)
    if payment_attempt and payment_attempt.seller_id != order.seller_id:
        logger.warning(
            "Payment attempt seller mismatch — possible cross-tenant",
            extra={"order_id": internal_order_id, "attempt_seller": payment_attempt.seller_id, "order_seller": order.seller_id},
        )
        return {"success": False, "error": "seller mismatch"}

    # Decimal amount validation — never via float
    incoming_amount = _parse_decimal_amount(getattr(result, "amount", None))
    expected_amount = _parse_decimal_amount(order.total)

    if result.status == PaymentStatus.PAID and incoming_amount is None:
        return {"success": False, "error": "Paid amount could not be verified"}

    legacy_amount_mismatch = (
        payment_attempt is None
        and result.status == PaymentStatus.PAID
        and incoming_amount is not None
        and expected_amount is not None
        and incoming_amount != expected_amount
    )
    if legacy_amount_mismatch:
        logger.warning(
            f"Payment amount mismatch: expected {expected_amount} got {incoming_amount} for order {internal_order_id}",
            extra={"order_id": internal_order_id, "provider": provider},
        )
        return {"success": False, "error": f"Amount mismatch: {incoming_amount} vs {expected_amount}"}
    if payment_attempt and incoming_amount is not None and payment_attempt.amount != incoming_amount:
        return {"success": False, "error": f"Amount mismatch: {incoming_amount} vs {payment_attempt.amount}"}

    old_status = order.status.value if hasattr(order.status, 'value') else str(order.status)

    # Once payment has been accepted, gateway retries must not move the order
    # backward from any paid-lineage fulfilment state.
    paid_lineage = {"paid", "processing", "shipped", "delivered", "done"}
    is_old_paid = old_status in paid_lineage
    is_refunded = old_status == "refunded"

    restore_stock = False
    consume_restored_stock = False
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
        if is_old_paid:
            new_status = old_status
        else:
            consume_restored_stock = old_status == "cancelled"
            order.status = OrderStatus.PAID
            order.paid_at = datetime.now(timezone.utc)
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
        # A seller cancellation already restored stock, but a later verified
        # provider refund must still update financial state and the recovery ledger.
        if old_status in paid_lineage or old_status == "cancelled":
            order.status = OrderStatus.REFUNDED
            new_status = "refunded"
            restore_stock = old_status in paid_lineage
        else:
            new_status = old_status
    else:
        new_status = old_status

    # Row locking plus the current-state guard makes each real transition restore once.
    # Historical cancellation rows cannot be used here: a late paid event consumes the
    # restored stock again, so a later refund must perform a fresh restoration.
    stock_shortage_product_ids: list[int] = []
    late_paid_consumed_quantities: dict[int, int] = {}
    if restore_stock and old_status not in ("cancelled", "refunded"):
        consumed_quantities = await _get_late_paid_consumed_quantities(db, order.id)
        await _adjust_order_stock_for_payment(
            db,
            order,
            restore=True,
            quantities_by_product=consumed_quantities,
        )

    if consume_restored_stock:
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
            order.notes = f"{order.notes or ''} {shortage_note}".strip()
            logger.warning(
                "Late paid order has insufficient stock",
                extra={
                    "order_id": order.id,
                    "product_ids": stock_shortage_product_ids,
                },
            )

    late_paid_consumed_marker = ""
    if consume_restored_stock:
        consumed_entries = ",".join(
            f"{product_id}:{quantity}"
            for product_id, quantity in sorted(late_paid_consumed_quantities.items())
        )
        late_paid_consumed_marker = f"; late_paid_consumed={consumed_entries};"

    if new_status != old_status:
        history = OrderStatusHistory(
            order_id=order.id,
            from_status=old_status,
            to_status=new_status,
            changed_by=f"webhook_{provider}",
            note=(
                f"Payment {getattr(result.status, 'value', result.status)} via {provider}"
                + late_paid_consumed_marker
            ),
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
            metadata={
                "provider": provider,
                "invoice_id": invoice_id,
                "stock_shortage_product_ids": stock_shortage_product_ids,
                "late_paid_consumed_quantities": late_paid_consumed_quantities,
            },
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
        "stock_shortage_product_ids": stock_shortage_product_ids,
    }

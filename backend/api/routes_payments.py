"""
JUALIN.AI — Payment API Routes
Create payments, check status, list payment methods.

Endpoints:
    POST /api/payments/create          → Create payment for an order
    GET  /api/payments/{order_id}      → Get payment status
    GET  /api/payments/methods         → List available payment methods
    GET  /api/payments/config          → Get client-side payment config
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import secrets

from config import get_settings
from models.database import get_db
from models.user import User
from models.order import Order, OrderStatus
from api.routes_auth import get_current_user
from core.logging_config import get_logger
from core.exceptions import NotFoundError, PaymentError, ValidationError

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)


# ── Pydantic Schemas ──

class CreatePaymentRequest(BaseModel):
    order_id: int
    method: str = "qris"           # qris, snap, va_bca, etc.
    provider: Optional[str] = None  # midtrans, cashi (auto-detect if not set)


class PaymentStatusResponse(BaseModel):
    order_id: int
    status: str
    provider: Optional[str]
    method: Optional[str]
    payment_url: Optional[str]
    amount: float


class PublicCreatePaymentRequest(BaseModel):
    order_id: int
    token: str
    method: str = "qris"
    provider: Optional[str] = None


def _verify_public_token(order: Order, token: str | None):
    if (
        not token
        or not order.payment_access_token
        or not secrets.compare_digest(str(token), str(order.payment_access_token))
    ):
        raise HTTPException(status_code=403, detail="Link pembayaran tidak valid atau sudah tidak berlaku")


def _payment_payload(order: Order, payment_created: bool = True, check_error: str | None = None) -> dict:
    data = {
        "order_id": order.id,
        "status": order.status.value,
        "provider": order.payment_provider,
        "method": order.payment_method,
        "invoice_id": order.payment_invoice_id,
        "payment_url": order.payment_url,
        "qr_data": order.payment_qr_data,
        "va_number": order.payment_va_number,
        "expires_at": order.payment_expires_at,
        "amount": order.total,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "payment_created": payment_created,
    }
    if check_error:
        data["check_error"] = check_error
    return data


def _available_payment_methods() -> list[dict]:
    methods = []

    if settings.CASHI_API_KEY:
        methods.extend([
            {
                "provider": "cashi",
                "method": "qris",
                "label": "QRIS (Semua E-Wallet & Mobile Banking)",
                "icon": "📱",
                "description": "GoPay, OVO, Dana, ShopeePay, dan semua bank",
            },
            {
                "provider": "cashi",
                "method": "va_bca",
                "label": "Transfer Bank BCA (VA)",
                "icon": "🏦",
                "description": "Virtual Account BCA",
            },
            {
                "provider": "cashi",
                "method": "va_bni",
                "label": "Transfer Bank BNI (VA)",
                "icon": "🏦",
                "description": "Virtual Account BNI",
            },
            {
                "provider": "cashi",
                "method": "va_bri",
                "label": "Transfer Bank BRI (VA)",
                "icon": "🏦",
                "description": "Virtual Account BRI",
            },
            {
                "provider": "cashi",
                "method": "va_mandiri",
                "label": "Transfer Bank Mandiri (VA)",
                "icon": "🏦",
                "description": "Virtual Account Mandiri",
            },
        ])

    if settings.MIDTRANS_SERVER_KEY:
        methods.extend([
            {
                "provider": "midtrans",
                "method": "snap",
                "label": "Midtrans (Semua Metode)",
                "icon": "💳",
                "description": "QRIS, GoPay, Transfer Bank, Kartu Kredit, dan lainnya",
            },
        ])

    return methods


async def _sync_payment_status(order: Order, db: AsyncSession | None = None) -> dict:
    if not order.payment_provider:
        return _payment_payload(order, payment_created=False)

    from services.payments.factory import get_payment_gateway
    from services.payments.base import PaymentStatus

    try:
        gateway = get_payment_gateway(order.payment_provider)
        invoice_id = order.payment_invoice_id or f"JUALIN-{order.id}"
        status_result = await gateway.check_status(invoice_id)

        if db:
            old_status = order.status.value if hasattr(order.status, "value") else str(order.status)
            new_status = old_status
            restore_stock = False

            if old_status in {"paid", "shipped", "done"} and status_result.status in (
                PaymentStatus.PENDING,
                PaymentStatus.EXPIRED,
                PaymentStatus.CANCELLED,
                PaymentStatus.FAILED,
            ):
                new_status = old_status
            elif status_result.status == PaymentStatus.PAID:
                order.status = OrderStatus.PAID
                order.paid_at = datetime.now(timezone.utc)
                new_status = "paid"
            elif status_result.status in (PaymentStatus.EXPIRED, PaymentStatus.CANCELLED):
                order.status = OrderStatus.CANCELLED
                new_status = "cancelled"
                restore_stock = True
            elif status_result.status == PaymentStatus.REFUNDED:
                order.status = OrderStatus.REFUNDED
                new_status = "refunded"
                restore_stock = True

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
                        product.stok += int(item.get("qty", 1))

            if new_status != old_status:
                from models.order_status_history import OrderStatusHistory

                db.add(OrderStatusHistory(
                    order_id=order.id,
                    from_status=old_status,
                    to_status=new_status,
                    changed_by=f"payment_status_{order.payment_provider}",
                    note=f"Payment {status_result.status.value} via status check",
                ))
                from core.audit import record_audit
                await record_audit(
                    db,
                    action="payment.status.changed",
                    entity_type="order",
                    entity_id=order.id,
                    seller_id=order.seller_id,
                    actor_type="payment_status_check",
                    before={"status": old_status},
                    after={"status": new_status},
                    metadata={"provider": order.payment_provider, "invoice_id": invoice_id},
                )
                await db.commit()
                await db.refresh(order)

        return {
            **_payment_payload(order, payment_created=True),
            "status": status_result.status.value,
            "provider": status_result.provider,
            "method": status_result.method or order.payment_method,
            "amount": status_result.amount or order.total,
            "paid_at": status_result.paid_at or (order.paid_at.isoformat() if order.paid_at else None),
        }

    except PaymentError as e:
        return _payment_payload(order, payment_created=True, check_error=str(e))


# ══════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════

@router.post("/create")
async def create_payment(
    req: CreatePaymentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a payment for an existing order.
    Returns payment URL/QR/token based on the method chosen.
    
    Seller creates payment → gets link/QR → sends to customer.
    """
    # Find order (must belong to current seller)
    result = await db.execute(
        select(Order)
        .where(Order.id == req.order_id)
        .where(Order.seller_id == current_user.id)
    )
    order = result.scalar_one_or_none()

    if not order:
        raise NotFoundError("Order", req.order_id)

    # Validate order is in a payable state
    if order.status not in (OrderStatus.PENDING, OrderStatus.CONFIRMED):
        raise ValidationError(
            message=f"Order #{req.order_id} tidak dalam status yang bisa dibayar (status: {order.status.value})",
            fields={"status": order.status.value},
        )

    # Don't create duplicate payments
    if order.payment_url and order.payment_provider:
        return {
            "message": "Pembayaran sudah dibuat sebelumnya",
            **_payment_payload(order, payment_created=True),
            "already_exists": True,
        }

    # Create payment
    from services.payments.factory import create_payment_for_order

    payment_result = await create_payment_for_order(
        order=order,
        method=req.method,
        provider=req.provider,
        db=db,
    )

    logger.info(
        f"Payment created: order #{req.order_id} via {payment_result['provider']}/{payment_result['method']}",
        extra={
            "order_id": req.order_id,
            "provider": payment_result["provider"],
            "method": payment_result["method"],
            "amount": payment_result["amount"],
        },
    )

    return payment_result


@router.get("/status/{order_id}")
async def get_payment_status(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    P1.4 — Read-only persisted snapshot, zero provider/network call and zero DB mutation.
    Reconciliation moved to POST /status/{order_id}/refresh
    """
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .where(Order.seller_id == current_user.id)
    )
    order = result.scalar_one_or_none()

    if not order:
        raise NotFoundError("Order", order_id)

    # Read-only: no provider sync, no mutation
    return _payment_payload(order, payment_created=bool(order.payment_url))


@router.post("/status/{order_id}/refresh")
async def refresh_payment_status(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    P1.4 — Seller-auth explicit refresh: durable deduplicated reconciliation job.
    Returns 202 refreshing, does not claim paid before verified provider fact.
    """
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .where(Order.seller_id == current_user.id)
    )
    order = result.scalar_one_or_none()

    if not order:
        raise NotFoundError("Order", order_id)

    if not order.payment_provider or not order.payment_invoice_id:
        return {"status": "no_payment", "message": "Belum ada pembayaran yang dibuat", "order_id": order_id}

    # Enqueue durable reconciliation job (idempotent)
    from core.idempotency import enqueue_job_record

    idem_key = f"payment_refresh:{order.seller_id}:{order.id}:{order.payment_invoice_id}"
    job, is_new = await enqueue_job_record(
        db,
        job_type="payment_reconciliation",
        payload={"order_id": order.id, "invoice_id": order.payment_invoice_id, "provider": order.payment_provider},
        seller_id=order.seller_id,
        idempotency_key=idem_key,
        handler_contract_version=1,
        retryable=False,
    )
    await db.commit()

    return {
        "status": "refreshing",
        "message": "Status pembayaran sedang diperbarui",
        "order_id": order_id,
        "job_id": job.id,
        "is_new": is_new,
    }



@router.get("/public/status/{order_id}")
async def get_public_payment_status(
    order_id: int,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """P1.4 — Public read-only snapshot, zero provider call, no mutation, no-store."""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()

    if not order:
        raise NotFoundError("Order", order_id)

    _verify_public_token(order, token)
    # Read-only, no sync
    return _payment_payload(order, payment_created=bool(order.payment_url))


@router.post("/public/status/{order_id}/refresh")
async def refresh_public_payment_status(
    order_id: int,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    P1.4 — Public refresh: capability session + Origin/CSRF + rate limit,
    durable deduplicated job, 202, zero inline provider sync.
    Until capability session implemented (P2.4), fail-closed with 501.
    """
    # Until P2.4 capability exchange exists, this endpoint is absent/fail-closed
    # Return 501 to indicate not yet implemented, zero sync
    from fastapi import HTTPException

    raise HTTPException(
        status_code=501,
        detail={
            "error": "not_implemented",
            "message": "Public payment refresh belum tersedia — menunggu capability session (P2.4)",
        },
    )


@router.get("/public/methods/{order_id}")
async def list_public_payment_methods(
    order_id: int,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """List payment methods available to a customer with a valid payment link."""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()

    if not order:
        raise NotFoundError("Order", order_id)

    _verify_public_token(order, token)
    methods = _available_payment_methods()
    return {"methods": methods, "configured": bool(methods)}


@router.post("/public/create")
async def create_public_payment(
    req: PublicCreatePaymentRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a payment from the public payment page without seller login."""
    result = await db.execute(select(Order).where(Order.id == req.order_id))
    order = result.scalar_one_or_none()

    if not order:
        raise NotFoundError("Order", req.order_id)

    _verify_public_token(order, req.token)

    if order.status not in (OrderStatus.PENDING, OrderStatus.CONFIRMED):
        raise ValidationError(
            message=f"Order #{req.order_id} tidak dalam status yang bisa dibayar (status: {order.status.value})",
            fields={"status": order.status.value},
        )

    if order.payment_url and order.payment_provider:
        return {
            "message": "Pembayaran sudah dibuat sebelumnya",
            **_payment_payload(order, payment_created=True),
            "already_exists": True,
        }

    if req.provider == "manual" or req.method == "manual":
        raise ValidationError(
            message="Payment gateway belum dikonfigurasi. Hubungi seller untuk pembayaran manual.",
            fields={"provider": req.provider or "manual"},
        )

    from services.payments.factory import create_payment_for_order

    return await create_payment_for_order(
        order=order,
        method=req.method,
        provider=req.provider,
        db=db,
    )


@router.get("/methods")
async def list_payment_methods(
    current_user: User = Depends(get_current_user),
):
    """
    List available payment methods grouped by provider.
    Frontend uses this to show payment options.
    """
    methods = []

    # Cashi.id methods (always available if configured)
    if settings.CASHI_API_KEY:
        methods.extend([
            {
                "provider": "cashi",
                "method": "qris",
                "label": "QRIS (Semua E-Wallet & Mobile Banking)",
                "icon": "📱",
                "description": "GoPay, OVO, Dana, ShopeePay, dan semua bank",
            },
            {
                "provider": "cashi",
                "method": "va_bca",
                "label": "Transfer Bank BCA (VA)",
                "icon": "🏦",
                "description": "Virtual Account BCA",
            },
            {
                "provider": "cashi",
                "method": "va_bni",
                "label": "Transfer Bank BNI (VA)",
                "icon": "🏦",
                "description": "Virtual Account BNI",
            },
            {
                "provider": "cashi",
                "method": "va_bri",
                "label": "Transfer Bank BRI (VA)",
                "icon": "🏦",
                "description": "Virtual Account BRI",
            },
            {
                "provider": "cashi",
                "method": "va_mandiri",
                "label": "Transfer Bank Mandiri (VA)",
                "icon": "🏦",
                "description": "Virtual Account Mandiri",
            },
        ])

    # Midtrans methods
    if settings.MIDTRANS_SERVER_KEY:
        methods.extend([
            {
                "provider": "midtrans",
                "method": "snap",
                "label": "Midtrans (Semua Metode)",
                "icon": "💳",
                "description": "QRIS, GoPay, Transfer Bank, Kartu Kredit, dan lainnya",
            },
        ])

    return {"methods": methods, "configured": bool(methods)}


@router.get("/config")
async def get_payment_config(
    current_user: User = Depends(get_current_user),
):
    """
    Get client-side payment configuration.
    Frontend needs this for Midtrans Snap.js initialization.
    """
    return {
        "midtrans": {
            "enabled": bool(settings.MIDTRANS_SERVER_KEY),
            "client_key": settings.MIDTRANS_CLIENT_KEY if settings.MIDTRANS_SERVER_KEY else None,
            "is_production": settings.MIDTRANS_IS_PRODUCTION,
            "snap_url": "https://app.midtrans.com/snap/snap.js" if settings.MIDTRANS_IS_PRODUCTION
                        else "https://app.sandbox.midtrans.com/snap/snap.js",
        },
        "cashi": {
            "enabled": bool(settings.CASHI_API_KEY),
        },
        "default_provider": settings.DEFAULT_PAYMENT_PROVIDER,
    }

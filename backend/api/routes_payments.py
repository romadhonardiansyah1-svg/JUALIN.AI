"""
JUALIN.AI — Payment API Routes
Create payments, check status, list payment methods.

Endpoints:
    POST /api/payments/create          → Create payment for an order
    GET  /api/payments/{order_id}      → Get payment status
    GET  /api/payments/methods         → List available payment methods
    GET  /api/payments/config          → Get client-side payment config
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

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
    if order.payment_url and order.status == OrderStatus.PENDING:
        return {
            "message": "Pembayaran sudah dibuat sebelumnya",
            "order_id": order.id,
            "provider": order.payment_provider,
            "method": order.payment_method,
            "payment_url": order.payment_url,
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
    Check real-time payment status from the payment provider.
    Also syncs the status back to our database.
    """
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .where(Order.seller_id == current_user.id)
    )
    order = result.scalar_one_or_none()

    if not order:
        raise NotFoundError("Order", order_id)

    # If no payment was created yet
    if not order.payment_provider:
        return {
            "order_id": order_id,
            "status": order.status.value,
            "message": "Belum ada pembayaran yang dibuat untuk order ini",
            "payment_created": False,
        }

    # Check with provider
    from services.payments.factory import get_payment_gateway

    try:
        gateway = get_payment_gateway(order.payment_provider)
        invoice_id = f"JUALIN-{order_id}"

        status_result = await gateway.check_status(invoice_id)

        return {
            "order_id": order_id,
            "status": status_result.status.value,
            "provider": status_result.provider,
            "method": status_result.method or order.payment_method,
            "amount": status_result.amount or order.total,
            "paid_at": status_result.paid_at,
            "payment_url": order.payment_url,
            "payment_created": True,
        }

    except PaymentError as e:
        # Gateway not configured — return local data only
        return {
            "order_id": order_id,
            "status": order.status.value,
            "provider": order.payment_provider,
            "method": order.payment_method,
            "amount": order.total,
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "payment_url": order.payment_url,
            "payment_created": True,
            "check_error": str(e),
        }


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

    # Fallback if nothing configured
    if not methods:
        methods.append({
            "provider": "manual",
            "method": "manual",
            "label": "Transfer Manual",
            "icon": "💰",
            "description": "Hubungi seller untuk info pembayaran",
        })

    return {"methods": methods}


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

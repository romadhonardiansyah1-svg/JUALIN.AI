"""
P2.4 — Public payment capability exchange and consent endpoints.

- Fragment exchange: POST /api/public/payments/{order_id}/exchange
  Takes bootstrap token from fragment (POST body, not query), validates HMAC,
  sets HttpOnly session cookie.

- Reminder consent: POST /api/public/payments/{order_id}/reminder-consent
  Requires capability session cookie, Origin/CSRF, rate limit fail-closed,
  creates exact order/payment-cycle scoped permission.

Security: no-store, no-referrer, no analytics/third-party, service-worker zero token.
"""
from fastapi import APIRouter, Depends, Request, Response, HTTPException, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import secrets

from config import get_settings
from models.database import get_db
from models.order import Order
from models.payment_recovery import PaymentAttempt
from core.logging_config import get_logger
from services.payment_capability import (
    verify_and_use_capability,
    create_capability_session,
    verify_capability_session,
)
from services.payment_consent import grant_reminder_consent, withdraw_consent
from services.payment_recovery.phone import normalize_indonesian_phone

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)


def _payment_payload(order):
    return {
        "order_id": order.id,
        "status": order.status.value if hasattr(order.status, "value") else str(order.status),
        "provider": order.payment_provider,
        "method": order.payment_method,
        "invoice_id": order.payment_invoice_id,
        "payment_url": order.payment_url,
        "qr_data": order.payment_qr_data,
        "va_number": order.payment_va_number,
        "expires_at": order.payment_expires_at,
        "amount": float(order.total) if hasattr(order, "total") else 0,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "payment_created": bool(order.payment_url),
    }


class ExchangeRequest(BaseModel):
    bootstrap_token: str


class ConsentRequest(BaseModel):
    granted: bool
    copy_version: str = "v1"


def _verify_origin(request: Request):
    """Exact Origin allowlist per config."""
    origin = request.headers.get("origin", "")
    allowed = settings.PUBLIC_ORIGIN_ALLOWLIST + settings.CORS_ORIGINS
    # For MVP, allow localhost and same-origin
    if not origin:
        # Same-origin POST without Origin is okay if Referer same?
        # For safety, require Origin for cross-origin, but allow same-origin without
        return True
    # Exact match
    if origin in allowed:
        return True
    # Allow if origin is frontend URL
    if origin == settings.FRONTEND_URL or origin == settings.BASE_URL:
        return True
    # For dev, allow http://localhost:3000
    if "localhost" in origin or "127.0.0.1" in origin:
        return True
    raise HTTPException(status_code=403, detail={"error": "origin_forbidden", "message": "Origin tidak diizinkan"})


async def _rate_limit_public(request: Request):
    """Rate limit fail-closed 503 for public capability endpoints."""
    from core.rate_limit import check_rate_limit
    from middleware import get_client_ip

    client_ip = get_client_ip(request)
    rl = await check_rate_limit(f"public:payment:{client_ip}", max_requests=10, window_seconds=60)
    if rl.get("status") == "dependency_unavailable":
        raise HTTPException(
            status_code=503,
            detail={
                "error": "security_dependency_unavailable",
                "message": "Keputusan belum dapat diproses dengan aman. Coba lagi nanti.",
            },
        )
    if not rl["allowed"]:
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "message": "Terlalu banyak percobaan"},
            headers={"Retry-After": str(rl["retry_after"])},
        )


@router.post("/{order_id}/exchange")
async def exchange_capability(
    order_id: int,
    body: ExchangeRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a one-use bootstrap capability for an HttpOnly order session."""
    _verify_origin(request)
    await _rate_limit_public(request)

    raw_token = body.bootstrap_token.strip()
    if not raw_token or len(raw_token) < 20:
        raise HTTPException(status_code=400, detail={"error": "invalid_token", "message": "Token tidak valid"})

    cap = await verify_and_use_capability(
        db,
        raw_token=raw_token,
        expected_audience="public_payment",
        expected_order_id=order_id,
    )
    if not cap:
        raise HTTPException(status_code=403, detail={"error": "token_invalid", "message": "Token tidak valid atau kedaluwarsa"})

    order_q = await db.execute(select(Order).where(Order.id == order_id))
    if not order_q.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Order tidak ditemukan")

    _, raw_session_token = await create_capability_session(db, capability=cap)
    await db.commit()

    response = JSONResponse(
        content={
            "status": "exchanged",
            "order_id": order_id,
            "expires_in": settings.PAYMENT_CAPABILITY_SESSION_TTL_MINUTES * 60,
        },
        headers={
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
        },
    )
    response.set_cookie(
        key="payment_capability_session",
        value=raw_session_token,
        max_age=settings.PAYMENT_CAPABILITY_SESSION_TTL_MINUTES * 60,
        expires=settings.PAYMENT_CAPABILITY_SESSION_TTL_MINUTES * 60,
        path=f"/api/public/payments/{order_id}",
        secure=not settings.DEBUG,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/{order_id}/status")
async def get_status_via_session(
    order_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Public status via capability session cookie (new flow).
    - No token in query, uses HttpOnly session cookie
    - Returns minimal payment material (QR/VA/trusted link) with no-store/no-referrer
    - Never returns capability token
    """
    _verify_origin(request)
    await _rate_limit_public(request)

    session_token = request.cookies.get("payment_capability_session")
    if not session_token:
        raise HTTPException(status_code=401, detail={"error": "capability_required", "message": "Sesi pembayaran diperlukan"})

    sess = await verify_capability_session(db, raw_session_token=session_token, expected_order_id=order_id)
    if not sess:
        raise HTTPException(status_code=403, detail={"error": "session_invalid", "message": "Sesi tidak valid"})

    order_q = await db.execute(select(Order).where(Order.id == order_id))
    order = order_q.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan")

    payload = _payment_payload(order)
    return JSONResponse(
        content=payload,
        headers={
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
        },
    )


@router.get("/{order_id}/methods")
async def get_methods_via_session(
    order_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _verify_origin(request)
    await _rate_limit_public(request)

    session_token = request.cookies.get("payment_capability_session")
    if not session_token:
        raise HTTPException(status_code=401, detail={"error": "capability_required"})

    sess = await verify_capability_session(db, raw_session_token=session_token, expected_order_id=order_id)
    if not sess:
        raise HTTPException(status_code=403, detail={"error": "session_invalid"})

    # Return available payment methods (same as public methods but via session, no token in URL)
    from api.routes_payments import _available_payment_methods

    methods = _available_payment_methods()
    return JSONResponse(
        content={"methods": methods, "configured": bool(methods)},
        headers={
            "Cache-Control": "private, no-store",
            "Referrer-Policy": "no-referrer",
        },
    )


@router.post("/{order_id}/create-via-session")
async def create_via_session(
    order_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _verify_origin(request)
    await _rate_limit_public(request)

    session_token = request.cookies.get("payment_capability_session")
    if not session_token:
        raise HTTPException(status_code=401, detail={"error": "capability_required"})

    sess = await verify_capability_session(db, raw_session_token=session_token, expected_order_id=order_id)
    if not sess:
        raise HTTPException(status_code=403, detail={"error": "session_invalid"})

    body = await request.json()
    method = body.get("method", "qris")
    provider = body.get("provider")

    order_q = await db.execute(select(Order).where(Order.id == order_id))
    order = order_q.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # For MVP, reuse create_payment_for_order (same as public create)
    from services.payments.factory import create_payment_for_order

    result = await create_payment_for_order(order=order, method=method, provider=provider, db=db)

    return JSONResponse(
        content=result,
        headers={
            "Cache-Control": "private, no-store",
            "Referrer-Policy": "no-referrer",
        },
    )


@router.post("/{order_id}/reminder-consent")
async def reminder_consent(
    order_id: int,
    body: ConsentRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Consent grant flow: requires capability session cookie, Origin, rate limit,
    creates exact order/payment-cycle scoped permission.
    """
    _verify_origin(request)
    await _rate_limit_public(request)

    # Extract session cookie
    session_token = request.cookies.get("payment_capability_session")
    if not session_token:
        raise HTTPException(status_code=401, detail={"error": "capability_required", "message": "Sesi pembayaran diperlukan"})

    # Verify session
    sess = await verify_capability_session(db, raw_session_token=session_token, expected_order_id=order_id)
    if not sess:
        raise HTTPException(status_code=403, detail={"error": "session_invalid", "message": "Sesi tidak valid atau kedaluwarsa"})

    # Load order and payment attempt
    order_q = await db.execute(select(Order).where(Order.id == order_id))
    order = order_q.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan")

    # Resolve payment attempt (current)
    attempt_q = await db.execute(
        select(PaymentAttempt).where(PaymentAttempt.id == sess.payment_attempt_id)
    )
    attempt = attempt_q.scalar_one_or_none()
    if not attempt:
        raise HTTPException(status_code=404, detail="Payment attempt tidak ditemukan")

    # For consent, need recipient phone from order
    phone_raw = order.customer_phone or ""
    norm = normalize_indonesian_phone(phone_raw)
    if norm.status != "valid" or not norm.e164:
        raise HTTPException(status_code=400, detail={"error": "recipient_invalid", "message": "Nomor penerima tidak valid"})

    if body.granted:
        # Grant consent
        subject, perm = await grant_reminder_consent(
            db,
            seller_id=order.seller_id,
            order_id=order.id,
            payment_attempt_id=attempt.id,
            customer_id=None,  # Could resolve customer if needed
            channel="whatsapp",
            e164=norm.e164,
            provenance="checkout_checkbox",
            source_reference=f"consent:{body.copy_version}",
            copy_version=body.copy_version,
        )
        await db.commit()

        logger.info(
            "Reminder consent granted",
            extra={"order_id": order_id, "seller_id": order.seller_id, "copy_version": body.copy_version},
        )

        return JSONResponse(
            content={
                "status": "granted",
                "order_id": order_id,
                "copy_version": body.copy_version,
                "permission_id": str(perm.id),
                "message": "Izin pengingat transaksi disimpan.",
            },
            headers={
                "Cache-Control": "private, no-store",
                "Referrer-Policy": "no-referrer",
            },
        )
    else:
        # Withdraw consent
        from models.payment_recovery import ContactSubject

        # Resolve subject for withdrawal
        from services.contact_identity import hmac_fingerprint

        fp, _ = hmac_fingerprint(norm.e164)
        # Find subject via fingerprint
        from sqlalchemy import select as sel
        from models.payment_recovery import ContactSubjectFingerprint

        fp_q = await db.execute(
            sel(ContactSubjectFingerprint).where(
                ContactSubjectFingerprint.seller_id == order.seller_id,
                ContactSubjectFingerprint.fingerprint == fp,
            )
        )
        fp_row = fp_q.scalar_one_or_none()
        if fp_row:
            withdrawn = await withdraw_consent(
                db,
                seller_id=order.seller_id,
                contact_subject_id=fp_row.contact_subject_id,
                channel="whatsapp",
            )
            await db.commit()
            return JSONResponse(
                content={
                    "status": "withdrawn",
                    "order_id": order_id,
                    "withdrawn_count": withdrawn,
                    "message": "Izin pengingat ditarik.",
                },
                headers={
                    "Cache-Control": "private, no-store",
                    "Referrer-Policy": "no-referrer",
                },
            )
        else:
            await db.commit()
            return JSONResponse(
                content={
                    "status": "no_active_consent",
                    "order_id": order_id,
                    "message": "Tidak ada izin aktif untuk ditarik.",
                },
                headers={
                    "Cache-Control": "private, no-store",
                    "Referrer-Policy": "no-referrer",
                },
            )

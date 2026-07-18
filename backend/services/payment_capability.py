"""
P2.4 — Public payment capability HMAC and session service.

Security:
- Token: 256-bit entropy, opaque, stored as HMAC-SHA256 + key_version, not plaintext
- Constant-time compare
- Audience binding
- Expiry not beyond payment_attempt expiry
- One-use for legacy query tokens, replay handling via receipt
- Fragment exchange to HttpOnly cookie session
"""
from __future__ import annotations
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.payment_recovery import PaymentCapability, PaymentCapabilitySession, PaymentAttempt

settings = get_settings()


def _hmac_sha256(key: str, msg: str) -> str:
    return hmac.new(key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_raw_token() -> str:
    """256-bit entropy token, urlsafe."""
    return secrets.token_urlsafe(32)


def hmac_token(token: str, key_version: int | None = None) -> tuple[str, int]:
    """
    Compute HMAC of raw token using current key version.
    Returns (hmac_hex, key_version).
    """
    version = key_version or settings.PAYMENT_CAPABILITY_HMAC_KEY_VERSION
    # In real KMS, would fetch key by version
    key = settings.PAYMENT_CAPABILITY_HMAC_KEY
    # Simple key versioning: if version !=1, could use different env var, but for MVP single key
    digest = _hmac_sha256(key, token)
    return digest, version


def verify_token_hmac(token: str, expected_hmac: str, key_version: int) -> bool:
    """Constant-time compare HMAC."""
    # For dual-read during rotation, try current and previous key?
    # For MVP, single key, but we implement constant-time
    calc, _ = hmac_token(token, key_version)
    return hmac.compare_digest(calc, expected_hmac)


async def create_capability(
    db: AsyncSession,
    *,
    seller_id: int,
    order_id: int,
    payment_attempt_id: uuid.UUID,
    audience: str = "public_payment",
    purpose: str = "payment_status",
    ttl_hours: int | None = None,
    is_legacy: bool = False,
) -> tuple[PaymentCapability, str]:
    """
    Create a new capability with HMAC stored, return (capability_row, raw_token).
    Raw token is only returned once, never stored.
    """
    ttl = ttl_hours or settings.PAYMENT_CAPABILITY_TOKEN_TTL_HOURS
    raw_token = generate_raw_token()
    token_hmac, key_version = hmac_token(raw_token)

    # Determine expiry: min(ttl, payment_attempt expiry)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl)

    # If payment_attempt has expiry, cap capability expiry to it
    attempt_q = await db.execute(select(PaymentAttempt).where(PaymentAttempt.id == payment_attempt_id))
    attempt = attempt_q.scalar_one_or_none()
    if attempt and attempt.payment_expires_at:
        # Capability expiry must not exceed attempt expiry
        if attempt.payment_expires_at < expires_at:
            expires_at = attempt.payment_expires_at

    cap = PaymentCapability(
        seller_id=seller_id,
        order_id=order_id,
        payment_attempt_id=payment_attempt_id,
        token_hmac=token_hmac,
        key_version=key_version,
        audience=audience,
        purpose=purpose,
        issued_at=datetime.now(timezone.utc),
        expires_at=expires_at,
        is_legacy_query_token=is_legacy,
    )
    db.add(cap)
    await db.flush()
    return cap, raw_token


async def verify_and_use_capability(
    db: AsyncSession,
    *,
    raw_token: str,
    expected_audience: str,
    expected_order_id: int,
    purpose: str | None = None,
) -> PaymentCapability | None:
    """Verify and atomically consume a bootstrap capability."""
    for version in [settings.PAYMENT_CAPABILITY_HMAC_KEY_VERSION]:
        token_hmac, _ = hmac_token(raw_token, version)
        result = await db.execute(
            select(PaymentCapability)
            .where(PaymentCapability.token_hmac == token_hmac)
            .with_for_update()
        )
        capability = result.scalar_one_or_none()
        if not capability:
            continue
        if not hmac.compare_digest(capability.token_hmac, token_hmac):
            continue
        if capability.audience != expected_audience:
            return None
        if capability.order_id != expected_order_id:
            return None
        if purpose and capability.purpose != purpose:
            return None

        now = datetime.now(timezone.utc)
        if capability.expires_at and capability.expires_at < now:
            return None
        if capability.revoked_at or capability.used_at:
            return None

        capability.used_at = now
        await db.flush()
        return capability
    return None


async def create_capability_session(
    db: AsyncSession,
    *,
    capability: PaymentCapability,
    ttl_minutes: int | None = None,
) -> tuple[PaymentCapabilitySession, str]:
    """
    Create short-lived HttpOnly session from validated capability (fragment exchange).
    Returns (session_row, raw_session_token).
    """
    ttl = ttl_minutes or settings.PAYMENT_CAPABILITY_SESSION_TTL_MINUTES
    raw_session_token = generate_raw_token()
    session_hmac, key_version = hmac_token(raw_session_token)

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl)

    # Cap session expiry to capability expiry and payment attempt expiry
    if capability.expires_at and capability.expires_at < expires_at:
        expires_at = capability.expires_at

    session = PaymentCapabilitySession(
        capability_id=capability.id,
        seller_id=capability.seller_id,
        order_id=capability.order_id,
        payment_attempt_id=capability.payment_attempt_id,
        session_token_hmac=session_hmac,
        key_version=key_version,
        audience="public_payment_session",
        purpose=capability.purpose,
        issued_at=datetime.now(timezone.utc),
        expires_at=expires_at,
    )
    db.add(session)
    await db.flush()
    return session, raw_session_token


async def verify_capability_session(
    db: AsyncSession,
    *,
    raw_session_token: str,
    expected_order_id: int,
) -> PaymentCapabilitySession | None:
    """Verify session, parent capability, and current payment attempt together."""
    for version in [settings.PAYMENT_CAPABILITY_HMAC_KEY_VERSION]:
        session_hmac, _ = hmac_token(raw_session_token, version)
        result = await db.execute(
            select(PaymentCapabilitySession, PaymentCapability, PaymentAttempt)
            .join(PaymentCapability, PaymentCapability.id == PaymentCapabilitySession.capability_id)
            .join(PaymentAttempt, PaymentAttempt.id == PaymentCapabilitySession.payment_attempt_id)
            .where(PaymentCapabilitySession.session_token_hmac == session_hmac)
        )
        row = result.first()
        if not row:
            continue
        session, capability, attempt = row
        if not hmac.compare_digest(session.session_token_hmac, session_hmac):
            continue
        if session.order_id != expected_order_id:
            return None

        now = datetime.now(timezone.utc)
        if session.expires_at and session.expires_at < now:
            return None
        if session.revoked_at or capability.revoked_at:
            return None
        if capability.expires_at and capability.expires_at < now:
            return None
        if capability.order_id != session.order_id or capability.payment_attempt_id != session.payment_attempt_id:
            return None
        if attempt.order_id != session.order_id or attempt.seller_id != session.seller_id:
            return None
        if not attempt.is_current:
            return None
        return session
    return None

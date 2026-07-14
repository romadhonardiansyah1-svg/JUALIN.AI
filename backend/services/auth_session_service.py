"""
P3.2 — Auth session service: rotating refresh family, HttpOnly cookies, CSRF.

- Short-lived access cookie (JWT)
- Opaque rotating refresh session, hash stored
- Family_id, rotation_counter, reuse detection revokes family
- CSRF secret per session
"""
from __future__ import annotations
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.auth_session import AuthSession
from config import get_settings

settings = get_settings()

ACCESS_TTL_MINUTES = 15
REFRESH_IDLE_DAYS = 30
REFRESH_ABSOLUTE_DAYS = 90  # absolute max


def _hash_token(token: str) -> str:
    """SHA256 hash of token for storage (not plaintext)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _hmac_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)  # ~384-bit entropy


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def hash_csrf_token(csrf_token: str) -> str:
    return _hash_token(csrf_token)


async def create_session_family(
    db: AsyncSession,
    *,
    user_id: int,
    seller_id: int | None,
    actor_user_id: int,
    effective_seller_id: int | None = None,
    auth_mode: str = "password",
    scopes: str | None = None,
    ip_hash: str | None = None,
    user_agent_hash: str | None = None,
) -> Tuple[AuthSession, str, str]:
    """
    Create new session family with first refresh token and CSRF token.
    Returns (AuthSession row, raw_refresh_token, raw_csrf_token)
    """
    raw_refresh = generate_refresh_token()
    raw_csrf = generate_csrf_token()

    refresh_hash = _hash_token(raw_refresh)
    csrf_hash = hash_csrf_token(raw_csrf)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=REFRESH_IDLE_DAYS)
    absolute_expires = now + timedelta(days=REFRESH_ABSOLUTE_DAYS)

    family_id = uuid.uuid4()

    session = AuthSession(
        user_id=user_id,
        seller_id=seller_id,
        family_id=family_id,
        rotation_counter=0,
        is_current=True,
        refresh_token_hash=refresh_hash,
        csrf_token_hash=csrf_hash,
        actor_user_id=actor_user_id,
        effective_seller_id=effective_seller_id or seller_id,
        auth_mode=auth_mode,
        scopes=scopes,
        created_at=now,
        last_used_at=now,
        expires_at=expires_at,
        absolute_expires_at=absolute_expires,
        ip_hash=ip_hash,
        user_agent_hash=user_agent_hash,
    )
    db.add(session)
    await db.flush()
    return session, raw_refresh, raw_csrf


async def rotate_refresh_token(
    db: AsyncSession,
    *,
    old_refresh_token: str,
) -> Tuple[AuthSession, str, str] | Tuple[None, str, str]:
    """
    Rotate refresh token transactionally.
    - Old token must be valid, not expired, not revoked, current
    - Creates new session row with incremented rotation_counter, same family_id, new hashes
    - Old row marked not current, but kept for reuse detection
    - Returns (new_session, new_raw_refresh, new_raw_csrf) or (None, "", "") if invalid
    - If old token reuse detected (already rotated and old token presented again), revoke entire family and return None (security event)
    """
    old_hash = _hash_token(old_refresh_token)

    # Find session by refresh hash
    q = await db.execute(select(AuthSession).where(AuthSession.refresh_token_hash == old_hash))
    old_session = q.scalar_one_or_none()

    if not old_session:
        return None, "", ""

    now = datetime.now(timezone.utc)

    # Check revoked
    if old_session.revoked_at:
        # Already revoked — possible reuse? Check if family has newer current?
        # For reuse detection, if old_session is not current but presented again, revoke family
        if not old_session.is_current:
            # Reuse detected — revoke entire family
            await _revoke_family(db, old_session.family_id, reason="reuse_detected")
            await db.commit()
            return None, "", ""
        return None, "", ""

    # Check expiry
    if old_session.expires_at < now or old_session.absolute_expires_at < now:
        return None, "", ""

    # If old session is not current, it's a replay of old token after rotation — reuse detection
    if not old_session.is_current:
        await _revoke_family(db, old_session.family_id, reason="reuse_detected")
        await db.commit()
        return None, "", ""

    # Valid — rotate
    # Mark old as not current
    old_session.is_current = False
    old_session.last_used_at = now

    # Create new
    new_raw_refresh = generate_refresh_token()
    new_raw_csrf = generate_csrf_token()
    new_hash = _hash_token(new_raw_refresh)
    new_csrf_hash = hash_csrf_token(new_raw_csrf)

    new_session = AuthSession(
        user_id=old_session.user_id,
        seller_id=old_session.seller_id,
        family_id=old_session.family_id,
        rotation_counter=old_session.rotation_counter + 1,
        is_current=True,
        refresh_token_hash=new_hash,
        csrf_token_hash=new_csrf_hash,
        actor_user_id=old_session.actor_user_id,
        effective_seller_id=old_session.effective_seller_id,
        auth_mode=old_session.auth_mode,
        impersonation_id=old_session.impersonation_id,
        scopes=old_session.scopes,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=REFRESH_IDLE_DAYS),
        absolute_expires_at=old_session.absolute_expires_at,
        ip_hash=old_session.ip_hash,
        user_agent_hash=old_session.user_agent_hash,
    )
    db.add(new_session)
    await db.flush()
    return new_session, new_raw_refresh, new_raw_csrf


async def _revoke_family(db: AsyncSession, family_id: uuid.UUID, reason: str = "revoked"):
    """Revoke entire family."""
    from sqlalchemy import text

    await db.execute(
        text(
            "UPDATE auth_sessions SET revoked_at=now(), revoked_reason=:reason, is_current=false WHERE family_id=:family_id AND revoked_at IS NULL"
        ),
        {"family_id": str(family_id), "reason": reason},
    )


async def revoke_session(db: AsyncSession, session_id: uuid.UUID):
    q = await db.execute(select(AuthSession).where(AuthSession.id == session_id))
    sess = q.scalar_one_or_none()
    if sess and not sess.revoked_at:
        sess.revoked_at = datetime.now(timezone.utc)
        sess.revoked_reason = "logout"
        sess.is_current = False
        await db.flush()


async def revoke_all_for_user(db: AsyncSession, user_id: int):
    from sqlalchemy import text

    await db.execute(
        text("UPDATE auth_sessions SET revoked_at=now(), revoked_reason='revoke_all', is_current=false WHERE user_id=:uid AND revoked_at IS NULL"),
        {"uid": user_id},
    )


async def verify_csrf(db: AsyncSession, session_id: uuid.UUID, csrf_token: str) -> bool:
    q = await db.execute(select(AuthSession).where(AuthSession.id == session_id))
    sess = q.scalar_one_or_none()
    if not sess or sess.revoked_at:
        return False
    expected_hash = sess.csrf_token_hash
    if not expected_hash:
        return False
    calc_hash = hash_csrf_token(csrf_token)
    return hmac.compare_digest(calc_hash, expected_hash)

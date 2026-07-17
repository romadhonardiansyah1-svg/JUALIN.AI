"""
JUALIN.AI — Auth API Routes
Register, Login, JWT token management
"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
import jwt
from jwt import InvalidTokenError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import re
import asyncio
import hashlib
import uuid as uuid_module

from config import get_settings
from models.database import get_db
from models.user import User, UserTier, UserRole
from middleware import get_client_ip
from services.auth_session_service import create_session_family

router = APIRouter()
settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def _get_cookie_names():
    """Return cookie names based on DEBUG / production."""
    if settings.DEBUG:
        return {
            "access": "jualin_access",
            "refresh": "jualin_refresh",
            "csrf": "jualin_csrf",
        }
    else:
        return {
            "access": "__Host-jualin_access",
            "refresh": "__Host-jualin_refresh",
            "csrf": "jualin_csrf",
        }


def _set_auth_cookies(response, access_token: str, refresh_token: str, csrf_token: str):
    """Set Secure HttpOnly cookies per P3.2 contract."""
    names = _get_cookie_names()
    is_secure = not settings.DEBUG
    # Access: 15 min
    response.set_cookie(
        key=names["access"],
        value=access_token,
        max_age=15 * 60,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        path="/",
    )
    # Refresh: 30 days
    response.set_cookie(
        key=names["refresh"],
        value=refresh_token,
        max_age=30 * 24 * 3600,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        path="/",
    )
    # CSRF: not HttpOnly
    response.set_cookie(
        key=names["csrf"],
        value=csrf_token,
        max_age=30 * 24 * 3600,
        httponly=False,
        secure=is_secure,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response):
    names = _get_cookie_names()
    for key in [names["access"], names["refresh"], names["csrf"]]:
        response.delete_cookie(key=key, path="/")


# ── Pydantic Schemas ──

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    nama_toko: str
    no_hp: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    nama_toko: str
    slug: str
    tier: str
    role: str
    ai_active: bool
    ai_style: str
    no_hp: str
    deskripsi_toko: str = ""
    impersonation: bool = False
    impersonated_by: int | None = None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    user: UserResponse


# ── Helpers ──

def create_slug(nama_toko: str) -> str:
    """Convert store name to URL-safe slug."""
    slug = nama_toko.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-') or "toko"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    user_id: int,
    *,
    expires_delta: timedelta | None = None,
    session_id: uuid_module.UUID | None = None,
    impersonation: bool = False,
    impersonated_by: int | None = None,
    target_seller_id: int | None = None,
) -> str:
    expire_delta = expires_delta or timedelta(minutes=15)
    expire = datetime.now(timezone.utc) + expire_delta
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "token_type": "access",
        "jti": uuid_module.uuid4().hex,
    }
    if session_id:
        payload["sid"] = str(session_id)
    if impersonation:
        payload.update({
            "impersonation": True,
            "impersonated_by": impersonated_by,
            "target_seller_id": target_seller_id or user_id,
        })
    elif not session_id:
        raise ValueError("browser access tokens must be bound to an active session")
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def build_user_response(user: User, request: Request | None = None) -> UserResponse:
    data = UserResponse.model_validate(user)
    auth_context = getattr(request.state, "auth_context", {}) if request else {}
    data.impersonation = bool(auth_context.get("impersonation", False))
    data.impersonated_by = auth_context.get("impersonated_by")
    return data


def _email_rate_key(email: str) -> str:
    digest = hashlib.sha256(email.encode("utf-8")).hexdigest()[:16]
    return f"auth:login:email:{digest}"


async def _record_auth_audit(
    db: AsyncSession,
    action: str,
    request: Request,
    user: User | None = None,
    email: str = "",
    success: bool = False,
):
    from core.audit import record_audit

    await record_audit(
        db,
        action=action,
        entity_type="auth",
        entity_id=str(user.id if user else email),
        seller_id=user.id if user else None,
        actor_user_id=user.id if user else None,
        actor_type="seller" if user else "anonymous",
        metadata={
            "success": success,
            "email_hash": hashlib.sha256(email.encode("utf-8")).hexdigest()[:16] if email else "",
            "client_ip": get_client_ip(request),
            "user_agent": request.headers.get("user-agent", "")[:200],
        },
    )


async def _decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    if payload.get("token_type") != "access":
        raise HTTPException(status_code=401, detail="Token tidak valid")
    return payload


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency: extract and validate JWT from Bearer OR HttpOnly cookie,
    with ambiguous_credentials check if both present and different principal.

    Transitional: accepts both cookie and Bearer, but rejects if they differ.
    """
    bearer_token = credentials.credentials if credentials else None

    # Try cookie
    cookie_names = _get_cookie_names()
    cookie_token = None
    cookies = getattr(request, "cookies", {}) or {}
    for name in [cookie_names["access"], "__Host-jualin_access", "jualin_access"]:
        if name in cookies:
            cookie_token = cookies.get(name)
            break

    # If both present, resolve both and reject if different principal
    bearer_payload = None
    cookie_payload = None

    if bearer_token:
        try:
            payload = jwt.decode(bearer_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            if payload.get("token_type") == "access":
                bearer_payload = payload
        except Exception:
            bearer_payload = None

    if cookie_token:
        try:
            payload = jwt.decode(cookie_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            if payload.get("token_type") == "access":
                cookie_payload = payload
        except Exception:
            cookie_payload = None

    if bearer_token and cookie_token:
        # Both present — check if same principal
        b_sub = bearer_payload.get("sub") if bearer_payload else None
        c_sub = cookie_payload.get("sub") if cookie_payload else None
        b_jti = bearer_payload.get("jti") if bearer_payload else None
        c_jti = cookie_payload.get("jti") if cookie_payload else None
        if b_sub != c_sub or b_jti != c_jti:
            # Ambiguous credentials — audit and reject
            try:
                from core.audit import record_audit

                await record_audit(
                    db,
                    action="auth.ambiguous_credentials",
                    entity_type="auth",
                    entity_id="ambiguous",
                    actor_type="anonymous",
                    metadata={"bearer_sub": b_sub, "cookie_sub": c_sub},
                )
                await db.commit()
            except Exception:
                pass
            raise HTTPException(status_code=401, detail={"error": "ambiguous_credentials", "message": "Kredensial ambigu"})

    # Choose token: prefer cookie if valid, else bearer
    token_payload = None
    token = None
    if cookie_payload:
        token_payload = cookie_payload
        token = cookie_token
    elif bearer_payload:
        token_payload = bearer_payload
        token = bearer_token
    else:
        # No valid token found — try bearer raw if present but invalid, else 401
        if bearer_token or cookie_token:
            raise HTTPException(status_code=401, detail="Token tidak valid")
        raise HTTPException(status_code=401, detail="Token tidak valid")

    try:
        user_id = int(token_payload.get("sub"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Token tidak valid")

    session_id = token_payload.get("sid")
    if not token_payload.get("impersonation"):
        if not session_id:
            raise HTTPException(status_code=401, detail="Sesi tidak terikat")
        try:
            parsed_session_id = uuid_module.UUID(str(session_id))
        except (ValueError, TypeError):
            raise HTTPException(status_code=401, detail="Sesi tidak valid")

        from models.auth_session import AuthSession

        now = datetime.now(timezone.utc)
        session_result = await db.execute(
            select(AuthSession).where(
                AuthSession.id == parsed_session_id,
                AuthSession.user_id == user_id,
                AuthSession.is_current.is_(True),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
                AuthSession.absolute_expires_at > now,
            )
        )
        if not session_result.scalar_one_or_none():
            raise HTTPException(status_code=401, detail="Sesi telah berakhir")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=401, detail="User tidak ditemukan")

    request.state.auth_context = {
        "jti": token_payload.get("jti", ""),
        "session_id": session_id,
        "impersonation": bool(token_payload.get("impersonation", False)),
        "impersonated_by": token_payload.get("impersonated_by"),
        "target_seller_id": token_payload.get("target_seller_id"),
    }

    return user


# ── Endpoints ──

@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Register seller baru + auto-create toko."""
    # Rate limit — fail closed 503 on dependency unavailable
    from core.rate_limit import check_rate_limit

    client_ip = get_client_ip(request)
    rl = await check_rate_limit(f"auth:register:{client_ip}", max_requests=5, window_seconds=60)
    if rl.get("status") == "dependency_unavailable":
        raise HTTPException(
            status_code=503,
            detail={
                "error": "security_dependency_unavailable",
                "message": "Keputusan belum dapat diproses dengan aman. Coba lagi nanti.",
            },
        )
    if not rl["allowed"]:
        raise HTTPException(status_code=429, detail="Terlalu banyak percobaan. Coba lagi nanti.")

    email = str(req.email).lower().strip()
    nama_toko = req.nama_toko.strip()
    if not nama_toko:
        raise HTTPException(status_code=400, detail="Nama toko wajib diisi")

    # Check email exists
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")
    
    # Validate password
    if len(req.password) < settings.MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"Password minimal {settings.MIN_PASSWORD_LENGTH} karakter")
    
    # Create slug from store name
    base_slug = create_slug(nama_toko)
    slug = base_slug
    
    # Check slug uniqueness
    suffix = 2
    while True:
        result = await db.execute(select(User).where(User.slug == slug))
        if not result.scalar_one_or_none():
            break
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    
    # Create user
    user = User(
        email=email,
        password_hash=hash_password(req.password),
        nama_toko=nama_toko,
        slug=slug,
        no_hp=req.no_hp,
        tier=UserTier.FREE,
        role=UserRole.SELLER,
    )
    
    db.add(user)

    # User, success audit, and initial session are one transaction. A failed
    # session creation must not leave an account that the caller was told failed.
    try:
        await db.flush()
        await db.refresh(user)
        await _record_auth_audit(
            db,
            "auth.register.success",
            request,
            user=user,
            email=email,
            success=True,
        )
        session, raw_refresh, raw_csrf = await create_session_family(
            db,
            user_id=user.id,
            seller_id=user.id if user.role == UserRole.SELLER else None,
            actor_user_id=user.id,
            effective_seller_id=user.id,
        )
        token = create_access_token(user.id, session_id=session.id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=503,
            detail={"error": "session_unavailable", "message": "Sesi belum dapat dibuat. Silakan login kembali."},
        )

    _set_auth_cookies(response, token, raw_refresh, raw_csrf)
    return TokenResponse(user=build_user_response(user, request))


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Login seller dengan email + password."""
    # Rate limit — fail closed on dependency unavailable
    from core.rate_limit import check_rate_limit

    client_ip = get_client_ip(request)
    email = str(req.email).lower().strip()
    ip_rl = await check_rate_limit(f"auth:login:ip:{client_ip}", max_requests=8, window_seconds=60)
    email_rl = await check_rate_limit(_email_rate_key(email), max_requests=5, window_seconds=60)
    if ip_rl.get("status") == "dependency_unavailable" or email_rl.get("status") == "dependency_unavailable":
        raise HTTPException(
            status_code=503,
            detail={
                "error": "security_dependency_unavailable",
                "message": "Keputusan belum dapat diproses dengan aman. Coba lagi nanti.",
            },
        )
    if not ip_rl["allowed"] or not email_rl["allowed"]:
        raise HTTPException(status_code=429, detail="Terlalu banyak percobaan. Coba lagi nanti.")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(req.password, user.password_hash):
        await asyncio.sleep(0.25)
        await _record_auth_audit(db, "auth.login.failed", request, user=user, email=email, success=False)
        await db.commit()
        raise HTTPException(status_code=401, detail="Email atau password salah")
    
    await _record_auth_audit(db, "auth.login.success", request, user=user, email=email, success=True)

    # Browser auth is cookie-only and tied to the durable session row.
    try:
        session, raw_refresh, raw_csrf = await create_session_family(
            db,
            user_id=user.id,
            seller_id=user.id if user.role == UserRole.SELLER else None,
            actor_user_id=user.id,
            effective_seller_id=user.id,
        )
        token = create_access_token(user.id, session_id=session.id)
        await db.commit()
        _set_auth_cookies(response, token, raw_refresh, raw_csrf)
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=503,
            detail={"error": "session_unavailable", "message": "Sesi belum dapat dibuat. Coba lagi nanti."},
        )

    return TokenResponse(user=build_user_response(user, request))


@router.post("/refresh")
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Rotate the HttpOnly refresh token under a row lock."""
    from services.auth_session_service import rotate_refresh_token

    cookie_names = _get_cookie_names()
    raw_refresh = next(
        (
            request.cookies.get(name)
            for name in (cookie_names["refresh"], "__Host-jualin_refresh", "jualin_refresh")
            if request.cookies.get(name)
        ),
        None,
    )
    if not raw_refresh:
        raise HTTPException(status_code=401, detail="Refresh token missing")

    try:
        new_session, new_raw_refresh, new_raw_csrf, rotation_error = (
            await rotate_refresh_token(db, old_refresh_token=raw_refresh)
        )
        if not new_session:
            await db.commit()
            if rotation_error == "already_rotated":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "refresh_already_rotated",
                        "message": "Sesi sudah diperbarui oleh tab lain",
                    },
                )
            _clear_auth_cookies(response)
            error_code = (
                "reuse_detected"
                if rotation_error == "reuse_detected"
                else "session_invalid"
            )
            raise HTTPException(
                status_code=401,
                detail={
                    "error": error_code,
                    "message": "Sesi telah berakhir, silakan login kembali",
                },
            )

        result = await db.execute(select(User).where(User.id == new_session.user_id))
        user = result.scalar_one_or_none()
        if not user:
            await db.rollback()
            _clear_auth_cookies(response)
            raise HTTPException(status_code=401, detail="User tidak ditemukan")

        new_access = create_access_token(
            new_session.user_id, session_id=new_session.id
        )
        await db.commit()
        _set_auth_cookies(response, new_access, new_raw_refresh, new_raw_csrf)
        return TokenResponse(user=build_user_response(user, request))
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Refresh gagal")


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    P3.2 — Logout revokes current session and clears exact cookie attributes.
    """
    from services.auth_session_service import revoke_session
    import uuid as uuid_module

    # Try to find session by refresh token hash
    cookie_names = _get_cookie_names()
    raw_refresh = None
    for name in [cookie_names["refresh"], "__Host-jualin_refresh", "jualin_refresh"]:
        if name in request.cookies:
            raw_refresh = request.cookies.get(name)
            break

    if raw_refresh:
        try:
            from services.auth_session_service import _hash_token

            refresh_hash = _hash_token(raw_refresh)
            from models.auth_session import AuthSession

            q = await db.execute(select(AuthSession).where(AuthSession.refresh_token_hash == refresh_hash))
            sess = q.scalar_one_or_none()
            if sess:
                await revoke_session(db, sess.id)
                await db.commit()
        except Exception:
            await db.rollback()

    _clear_auth_cookies(response)

    return {"message": "Logout berhasil"}


@router.get("/me", response_model=UserResponse)
async def get_me(request: Request, current_user: User = Depends(get_current_user)):
    """Get current logged-in user info."""
    return build_user_response(current_user, request)


class SettingsUpdateRequest(BaseModel):
    ai_active: bool | None = None
    ai_style: str | None = None
    deskripsi_toko: str | None = None
    no_hp: str | None = None


@router.patch("/settings", response_model=UserResponse)
async def update_settings(
    req: SettingsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user settings (AI style, active status, etc)."""
    if req.ai_active is not None:
        current_user.ai_active = req.ai_active
    if req.ai_style is not None:
        if req.ai_style not in ("formal", "santai", "gaul"):
            raise HTTPException(status_code=400, detail="ai_style harus: formal, santai, atau gaul")
        current_user.ai_style = req.ai_style
    if req.deskripsi_toko is not None:
        current_user.deskripsi_toko = req.deskripsi_toko
    if req.no_hp is not None:
        current_user.no_hp = req.no_hp
    
    await db.commit()
    await db.refresh(current_user)
    
    return build_user_response(current_user)

"""
JUALIN.AI — Auth API Routes
Register, Login, JWT token management
"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
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

router = APIRouter()
settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


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
    access_token: str
    token_type: str = "bearer"
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
    impersonation: bool = False,
    impersonated_by: int | None = None,
    target_seller_id: int | None = None,
) -> str:
    expire_delta = expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expire_delta
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "token_type": "access",
        "jti": uuid_module.uuid4().hex,
    }
    if impersonation:
        payload.update({
            "impersonation": True,
            "impersonated_by": impersonated_by,
            "target_seller_id": target_seller_id or user_id,
        })
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


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency: extract and validate JWT, return current user."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("token_type") != "access":
            raise HTTPException(status_code=401, detail="Token tidak valid")
        user_id = int(payload.get("sub"))
    except HTTPException:
        raise
    except (InvalidTokenError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Token tidak valid")
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(status_code=401, detail="User tidak ditemukan")

    request.state.auth_context = {
        "jti": payload.get("jti", ""),
        "impersonation": bool(payload.get("impersonation", False)),
        "impersonated_by": payload.get("impersonated_by"),
        "target_seller_id": payload.get("target_seller_id"),
    }
    
    return user


# ── Endpoints ──

@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
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
    await db.commit()
    await db.refresh(user)
    await _record_auth_audit(db, "auth.register.success", request, user=user, email=email, success=True)
    await db.commit()
    
    # Generate token
    token = create_access_token(user.id)
    
    return TokenResponse(
        access_token=token,
        user=build_user_response(user, request),
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
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
    await db.commit()
    token = create_access_token(user.id)
    
    return TokenResponse(
        access_token=token,
        user=build_user_response(user, request),
    )


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

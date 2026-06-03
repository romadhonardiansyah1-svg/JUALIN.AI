"""
JUALIN.AI — Auth API Routes
Register, Login, JWT token management
"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import jwt, JWTError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import re

from config import get_settings
from models.database import get_db
from models.user import User, UserTier, UserRole

router = APIRouter()
settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


# ── Pydantic Schemas ──

class RegisterRequest(BaseModel):
    email: str
    password: str
    nama_toko: str
    no_hp: str = ""


class LoginRequest(BaseModel):
    email: str
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
    return slug.strip('-')


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency: extract and validate JWT, return current user."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Token tidak valid")
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(status_code=401, detail="User tidak ditemukan")
    
    return user


# ── Endpoints ──

@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register seller baru + auto-create toko."""
    # Check email exists
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")
    
    # Validate password
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password minimal 6 karakter")
    
    # Create slug from store name
    slug = create_slug(req.nama_toko)
    
    # Check slug uniqueness
    result = await db.execute(select(User).where(User.slug == slug))
    if result.scalar_one_or_none():
        # Append number if slug taken
        import random
        slug = f"{slug}-{random.randint(100, 999)}"
    
    # Create user
    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        nama_toko=req.nama_toko,
        slug=slug,
        no_hp=req.no_hp,
        tier=UserTier.FREE,
        role=UserRole.SELLER,
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Generate token
    token = create_access_token(user.id)
    
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login seller dengan email + password."""
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email atau password salah")
    
    token = create_access_token(user.id)
    
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current logged-in user info."""
    return UserResponse.model_validate(current_user)


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
    
    return UserResponse.model_validate(current_user)

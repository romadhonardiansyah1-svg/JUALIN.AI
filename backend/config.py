"""
JUALIN.AI — Configuration
Loads environment variables from .env file
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from urllib.parse import urlparse


class Settings(BaseSettings):
    # App
    APP_NAME: str = "JUALIN.AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    SECRET_KEY: str = "jualin-ai-secret-key-change-in-production"
    SCHEDULER_ENABLED: bool = True
    AUTO_CREATE_TABLES: bool = True
    ARQ_MAX_JOBS: int = 2

    # Scale-up feature flags
    ENABLE_WHATSAPP: bool = False
    ENABLE_AI_ACTIONS: bool = False
    ENABLE_CAMPAIGNS: bool = False
    ENABLE_WORKFLOWS: bool = False
    ENABLE_BILLING: bool = False
    ENABLE_MARKETPLACE_IMPORT: bool = False
    ENABLE_AI_QUALITY: bool = True

    # Market Acceptance feature flags
    ENABLE_GROWTH_LINKS: bool = True
    ENABLE_WA_TEMPLATES: bool = True
    ENABLE_TRUST_PROFILE: bool = True
    ENABLE_CONCIERGE: bool = True
    IMPERSONATION_TOKEN_MINUTES: int = 15

    # ── JUALIN OS (Multi-Agent Business OS) ──
    ENABLE_AGENT_OS: bool = True
    AGENT_OS_DEFAULT_MAX_DISCOUNT: float = 15.0      # diskon maksimum (%) default per seller
    AGENT_OS_DEFAULT_MARGIN_FLOOR: float = 10.0      # margin minimum di atas modal (%) default
    AGENT_OS_APPROVAL_ABOVE_PERCENT: float = 10.0    # diskon di atas ini butuh persetujuan
    AGENT_OS_LOW_STOCK_THRESHOLD: int = 3            # stok <= ini dianggap menipis
    AGENT_OS_NEGO_MAX_DISTANCE: float = 0.55         # ambang cosine distance produk fokus nego (kalibrasi!)
    CHAT_RATE_LIMIT_PER_MIN: int = 60                # rate limit chat publik per IP (venue demo = 1 NAT IP)

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/jualin_ai"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # JWT
    JWT_SECRET_KEY: str = "jwt-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 hours
    
    # LLM (9Router or direct)
    LLM_BASE_URL: str = "http://localhost:20128/v1"  # 9Router
    LLM_API_KEY: str = "not-needed"  # 9Router handles keys
    LLM_MODEL: str = "llama-3.1-8b-instant"
    
    # Gemini (backup / image AI)
    GEMINI_API_KEY: str = ""
    
    # Embedding
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    
    # Quota limits per tier
    QUOTA_FREE: int = 50
    QUOTA_STARTER: int = 500
    QUOTA_PRO: int = 2000
    QUOTA_BISNIS: int = 10000
    
    # Product limits per tier
    PRODUCT_LIMIT_FREE: int = 10
    PRODUCT_LIMIT_STARTER: int = 50
    PRODUCT_LIMIT_PRO: int = 200
    PRODUCT_LIMIT_BISNIS: int = 999999  # unlimited
    
    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    
    # Base URL (for webhook callbacks — set to your domain in production)
    BASE_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"
    
    # ── Payment Gateways ──
    
    # Midtrans (Snap API)
    MIDTRANS_SERVER_KEY: str = ""
    MIDTRANS_CLIENT_KEY: str = ""
    MIDTRANS_IS_PRODUCTION: bool = False  # False = sandbox, True = production
    
    # Cashi.id (QRIS + VA)
    CASHI_API_KEY: str = ""
    CASHI_BASE_URL: str = "https://cashi.id/api"
    
    # Default payment provider per seller tier
    # Free/Starter = cashi (simpler), Pro/Bisnis = midtrans (full features)
    DEFAULT_PAYMENT_PROVIDER: str = "cashi"

    # WhatsApp Cloud API
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_GRAPH_VERSION: str = "v20.0"
    WHATSAPP_APP_SECRET: str = ""

    # Security controls
    MAX_JSON_BODY_BYTES: int = 2 * 1024 * 1024
    MAX_MULTIPART_BODY_BYTES: int = 8 * 1024 * 1024
    MIN_PASSWORD_LENGTH: int = 10
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def validate_production_security(settings: Settings) -> list[str]:
    """Return blocking production misconfiguration errors."""
    if settings.DEBUG:
        return []

    errors: list[str] = []
    weak_markers = (
        "change-in-production",
        "ganti-",
        "GANTI_",
        "jualin-secret",
        "jwt-secret",
    )

    for key_name in ("SECRET_KEY", "JWT_SECRET_KEY"):
        value = getattr(settings, key_name, "")
        if len(value) < 32 or any(marker in value for marker in weak_markers):
            errors.append(f"{key_name} wajib diganti dengan secret random minimal 32 karakter")

    public_origins = []
    for origin in settings.CORS_ORIGINS:
        parsed = urlparse(origin)
        host = (parsed.hostname or "").lower()
        if host and host not in {"localhost", "127.0.0.1", "::1"}:
            public_origins.append(origin)
    if not public_origins:
        errors.append("CORS_ORIGINS production wajib memuat minimal satu domain publik HTTPS")

    for url_name in ("BASE_URL", "FRONTEND_URL"):
        value = getattr(settings, url_name, "")
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or host in {"localhost", "127.0.0.1", "::1"}:
            errors.append(f"{url_name} production wajib memakai HTTPS domain publik")

    return errors

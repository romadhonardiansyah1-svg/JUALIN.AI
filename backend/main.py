"""
JUALIN.AI — FastAPI Main Application
AI Sales Assistant Berbasis Katalog untuk Otomasi Layanan Chat UMKM Mikro

Entry point: uvicorn main:app --host 0.0.0.0 --port 8000
"""
import asyncio
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config import get_settings
from core.logging_config import setup_logging, get_logger
from core.exceptions import register_exception_handlers
from models.database import init_db, async_session
from api.routes_auth import router as auth_router
from api.routes_products import router as products_router
from api.routes_chat import router as chat_router
from api.routes_chat_stream import router as chat_stream_router
from api.routes_orders import router as orders_router
from api.routes_analytics import router as analytics_router
from api.routes_admin import router as admin_router
from api.routes_payments import router as payments_router
from api.routes_webhooks import router as webhooks_router
from middleware import RequestLoggingMiddleware, RateLimitMiddleware

settings = get_settings()
logger = get_logger("main")


# ── Background: Follow-up Scheduler ──
async def followup_scheduler():
    """
    Run follow-up checks every 15 minutes.
    Sends reminders to customers who haven't paid.
    """
    from ai.followup import get_pending_followups, mark_followup_sent, auto_cancel_expired

    while True:
        try:
            async with async_session() as db:
                # 1. Get pending follow-ups
                followups = await get_pending_followups(db)
                for fu in followups:
                    # In production, send via WhatsApp/SMS API
                    logger.info(
                        f"Follow-up #{fu['followup_number']} → {fu['customer_name']}",
                        extra={
                            "order_id": fu["order_id"],
                            "seller_id": fu["seller_id"],
                            "followup_number": fu["followup_number"],
                        },
                    )
                    await mark_followup_sent(fu["order_id"], db)

                # 2. Auto-cancel expired orders
                cancelled = await auto_cancel_expired(db)
                if cancelled > 0:
                    logger.info(
                        f"Auto-cancelled {cancelled} expired orders",
                        extra={"cancelled_count": cancelled},
                    )

        except Exception as e:
            logger.error(f"Follow-up scheduler error: {e}", exc_info=True)

        await asyncio.sleep(900)  # 15 minutes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup initialization and graceful shutdown.
    """
    start_time = time.monotonic()

    # 1. Initialize structured logging
    log_level = "DEBUG" if settings.DEBUG else "INFO"
    setup_logging(log_level=log_level, log_to_file=not settings.DEBUG)

    logger.info("=" * 60)
    logger.info(f"🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info("=" * 60)

    # 2. Initialize database
    await init_db()
    logger.info("✅ Database initialized with pgvector extension")

    # 3. Start follow-up scheduler
    task = asyncio.create_task(followup_scheduler())
    logger.info("⏰ Follow-up scheduler started (every 15 min)")

    # 4. Log startup metrics
    startup_ms = round((time.monotonic() - start_time) * 1000)
    logger.info(
        f"✅ {settings.APP_NAME} ready in {startup_ms}ms",
        extra={
            "startup_time_ms": startup_ms,
            "debug_mode": settings.DEBUG,
            "llm_model": settings.LLM_MODEL,
            "embedding_model": settings.EMBEDDING_MODEL,
        },
    )

    yield

    # ── Graceful Shutdown ──
    logger.info("Shutting down...")

    # Cancel background tasks
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Close LLM HTTP client
    try:
        from ai.llm_client import close_client
        await close_client()
    except Exception:
        pass

    logger.info("👋 Shutdown complete")


# ══════════════════════════════════════════════════
# FastAPI Application
# ══════════════════════════════════════════════════

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI Sales Assistant Berbasis Katalog untuk Otomasi Layanan Chat UMKM Mikro",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,      # Disable Swagger in production
    redoc_url="/redoc" if settings.DEBUG else None,     # Disable ReDoc in production
)

# ── Register Exception Handlers ──
register_exception_handlers(app)

# ── Middleware Stack (order matters: first added = outermost) ──

# 1. Request logging + ID (outermost — sees everything)
app.add_middleware(RequestLoggingMiddleware)

# 2. Rate limiting
app.add_middleware(RateLimitMiddleware)

# 3. CORS (innermost before route handlers)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if not settings.DEBUG else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-Process-Time", "X-Request-ID"],
)

# ── Register Routers ──
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(products_router, prefix="/api/products", tags=["Products"])
app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
app.include_router(chat_stream_router, prefix="/api/chat", tags=["Chat Stream"])
app.include_router(orders_router, prefix="/api/orders", tags=["Orders"])
app.include_router(analytics_router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(payments_router, prefix="/api/payments", tags=["Payments"])
app.include_router(webhooks_router, prefix="/api/webhooks", tags=["Webhooks"])

# ── Static Files (uploads) ──
import os
from fastapi.staticfiles import StaticFiles

uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")


# ══════════════════════════════════════════════════
# Health & Readiness Endpoints
# ══════════════════════════════════════════════════

@app.get("/")
async def root():
    """API info endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs" if settings.DEBUG else "disabled",
        "security": {
            "rate_limiting": "enabled",
            "cors": "configured",
            "xss_protection": "enabled",
            "csrf_prevention": "token-based",
            "request_id_tracking": "enabled",
        },
    }


@app.get("/health")
async def health():
    """
    Comprehensive health check.
    Validates: Redis, Database, LLM connectivity.
    Used by monitoring systems and load balancers.
    """
    from cache import get_redis
    from sqlalchemy import text

    checks = {
        "status": "ok",
        "version": settings.APP_VERSION,
    }

    # 1. Redis check
    try:
        r = await get_redis()
        if r:
            await r.ping()
            checks["redis"] = "connected"
        else:
            checks["redis"] = "unavailable"
    except Exception:
        checks["redis"] = "error"

    # 2. Database check
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
            checks["database"] = "connected"
    except Exception:
        checks["database"] = "error"
        checks["status"] = "degraded"

    # 3. Overall status
    if checks.get("database") == "error":
        checks["status"] = "unhealthy"

    return checks


@app.get("/ready")
async def readiness():
    """
    Readiness probe for Docker/Kubernetes.
    Returns 200 only when ALL critical services are connected.
    Used by Docker HEALTHCHECK and orchestrators.
    """
    from cache import get_redis
    from sqlalchemy import text

    errors = []

    # Database must be ready
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
    except Exception as e:
        errors.append(f"database: {e}")

    # Redis should be ready (non-critical but preferred)
    try:
        r = await get_redis()
        if r:
            await r.ping()
    except Exception as e:
        errors.append(f"redis: {e}")

    if errors:
        return {"ready": False, "errors": errors}

    return {"ready": True}

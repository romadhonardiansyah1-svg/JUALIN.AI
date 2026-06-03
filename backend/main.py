"""
JUALIN.AI — FastAPI Main Application
AI Sales Assistant Berbasis Katalog untuk Otomasi Layanan Chat UMKM Mikro
"""
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config import get_settings
from models.database import init_db, async_session
from api.routes_auth import router as auth_router
from api.routes_products import router as products_router
from api.routes_chat import router as chat_router
from api.routes_orders import router as orders_router
from api.routes_analytics import router as analytics_router
from api.routes_admin import router as admin_router
from middleware import RateLimitMiddleware

settings = get_settings()


# ── Background: Follow-up Scheduler ──
async def followup_scheduler():
    """Run follow-up checks every 15 minutes."""
    from ai.followup import get_pending_followups, mark_followup_sent, auto_cancel_expired

    while True:
        try:
            async with async_session() as db:
                # 1. Get pending follow-ups
                followups = await get_pending_followups(db)
                for fu in followups:
                    # In production, send via WhatsApp/SMS API
                    print(f"📩 Follow-up #{fu['followup_number']} → {fu['customer_name']}: {fu['message'][:60]}...")
                    await mark_followup_sent(fu["order_id"], db)

                # 2. Auto-cancel expired orders
                cancelled = await auto_cancel_expired(db)
                if cancelled > 0:
                    print(f"🚫 Auto-cancelled {cancelled} expired orders")

        except Exception as e:
            print(f"⚠️ Follow-up scheduler error: {e}")

        await asyncio.sleep(900)  # 15 minutes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and start background tasks on startup."""
    await init_db()
    print("✅ Database initialized with pgvector extension")
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} is running!")

    # Start follow-up scheduler
    task = asyncio.create_task(followup_scheduler())
    print("⏰ Follow-up scheduler started (every 15 min)")

    yield

    # Cleanup
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    print("👋 Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI Sales Assistant Berbasis Katalog untuk Otomasi Layanan Chat UMKM Mikro",
    lifespan=lifespan,
)

# Middleware: Rate Limiter (outermost = processes first)
app.add_middleware(RateLimitMiddleware)

# Middleware: CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-Process-Time"],
)

# Register routers
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(products_router, prefix="/api/products", tags=["Products"])
app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
app.include_router(orders_router, prefix="/api/orders", tags=["Orders"])
app.include_router(analytics_router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])

# Static file serving for uploaded images
import os
from fastapi.staticfiles import StaticFiles

uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "security": {
            "rate_limiting": "enabled",
            "cors": "configured",
            "xss_protection": "enabled",
            "csrf_prevention": "token-based",
        },
    }


@app.get("/health")
async def health():
    """Health check — also validates Redis connection."""
    from cache import get_redis

    redis_status = "disconnected"
    try:
        r = await get_redis()
        if r:
            await r.ping()
            redis_status = "connected"
    except Exception:
        pass

    return {
        "status": "ok",
        "redis": redis_status,
        "version": settings.APP_VERSION,
    }

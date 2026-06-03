"""
JUALIN.AI — FastAPI Main Application
AI Sales Assistant Berbasis Katalog untuk Otomasi Layanan Chat UMKM Mikro
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config import get_settings
from models.database import init_db
from api.routes_auth import router as auth_router
from api.routes_products import router as products_router
from api.routes_chat import router as chat_router
from api.routes_orders import router as orders_router
from api.routes_analytics import router as analytics_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    print("✅ Database initialized with pgvector extension")
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} is running!")
    yield
    print("👋 Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI Sales Assistant Berbasis Katalog untuk Otomasi Layanan Chat UMKM Mikro",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(products_router, prefix="/api/products", tags=["Products"])
app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
app.include_router(orders_router, prefix="/api/orders", tags=["Orders"])
app.include_router(analytics_router, prefix="/api/analytics", tags=["Analytics"])


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}

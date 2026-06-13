"""
JUALIN.AI — Database Setup
SQLAlchemy async engine + session + Base model
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=10,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """Dependency: yields an async database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Create all tables and enable pgvector extension."""
    # Import the model package so every declarative table is registered before create_all().
    import models  # noqa: F401

    async with engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        if settings.AUTO_CREATE_TABLES:
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)

            # Lightweight forward-only schema patches for VPS installs that used create_all()
            # before these production payment fields existed.
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_invoice_id VARCHAR(100)"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_access_token VARCHAR(100)"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_qr_data TEXT"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_va_number VARCHAR(100)"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_expires_at VARCHAR(100)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_payment_invoice_id ON orders (payment_invoice_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_payment_access_token ON orders (payment_access_token)"))

            # ── Market Acceptance Schema Patches ──

            # Sprint 1: Quick-start onboarding
            await conn.execute(text("ALTER TABLE seller_onboarding ADD COLUMN IF NOT EXISTS store_category VARCHAR(50)"))
            await conn.execute(text("ALTER TABLE seller_onboarding ADD COLUMN IF NOT EXISTS seller_goal VARCHAR(255)"))
            await conn.execute(text("ALTER TABLE seller_onboarding ADD COLUMN IF NOT EXISTS tone VARCHAR(20)"))
            await conn.execute(text("ALTER TABLE seller_onboarding ADD COLUMN IF NOT EXISTS quick_start_completed BOOLEAN DEFAULT FALSE"))

            # Sprint 2: Template niche
            await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS niche VARCHAR(50)"))
            await conn.execute(text("ALTER TABLE templates ADD COLUMN IF NOT EXISTS pack_id VARCHAR(50)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_templates_niche ON templates (niche)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_templates_pack_id ON templates (pack_id)"))

            # Sprint 5: Order attribution
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS source VARCHAR(50)"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS assisted_by_ai INTEGER DEFAULT 0"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS campaign_id_ref INTEGER"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS growth_link_id INTEGER"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_source ON orders (source)"))

            # Sprint 5: Daily metrics AI impact
            await conn.execute(text("ALTER TABLE daily_seller_metrics ADD COLUMN IF NOT EXISTS ai_assisted_orders INTEGER DEFAULT 0"))
            await conn.execute(text("ALTER TABLE daily_seller_metrics ADD COLUMN IF NOT EXISTS ai_assisted_revenue FLOAT DEFAULT 0"))
            await conn.execute(text("ALTER TABLE daily_seller_metrics ADD COLUMN IF NOT EXISTS recovered_payment_value FLOAT DEFAULT 0"))
            await conn.execute(text("ALTER TABLE daily_seller_metrics ADD COLUMN IF NOT EXISTS ai_handoff_count INTEGER DEFAULT 0"))

            # ── JUALIN OS Schema Patches ──
            await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS cost_price FLOAT DEFAULT 0"))


"""
Daily aggregated seller metrics for analytics dashboard.
Pre-computed daily to avoid expensive real-time queries on VPS.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, JSON, UniqueConstraint
from sqlalchemy.sql import func

from models.database import Base


class DailySellerMetric(Base):
    __tablename__ = "daily_seller_metrics"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(String(10), nullable=False, index=True)  # "2026-06-05"

    chats_in = Column(Integer, default=0)
    ai_replies = Column(Integer, default=0)
    orders_created = Column(Integer, default=0)
    orders_paid = Column(Integer, default=0)
    orders_cancelled = Column(Integer, default=0)
    revenue_paid = Column(Float, default=0)
    pending_payment_value = Column(Float, default=0)
    campaign_sent = Column(Integer, default=0)
    campaign_conversions = Column(Integer, default=0)
    repeat_buyer_count = Column(Integer, default=0)
    top_products_json = Column(JSON, default=list)  # [{id, name, qty, revenue}]

    # AI impact metrics (Market Acceptance Sprint 5)
    ai_assisted_orders = Column(Integer, default=0)
    ai_assisted_revenue = Column(Float, default=0)
    recovered_payment_value = Column(Float, default=0)
    ai_handoff_count = Column(Integer, default=0)

    extra_json = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("seller_id", "date", name="uq_daily_metric_seller_date"),
    )

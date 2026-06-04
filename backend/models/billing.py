"""
Billing and usage quota models.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Float, UniqueConstraint
from sqlalchemy.sql import func

from models.database import Base


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), nullable=False, unique=True, index=True)
    name = Column(String(100), nullable=False)
    price_monthly = Column(Float, default=0)
    limits = Column(JSON, default=dict)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    plan_code = Column(String(50), nullable=False, index=True)
    status = Column(String(20), default="active")
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    override_limits = Column(JSON, default=dict)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class UsageCounter(Base):
    __tablename__ = "usage_counters"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    metric = Column(String(100), nullable=False, index=True)
    period = Column(String(20), nullable=False, index=True)
    used = Column(Integer, default=0)
    limit_value = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("seller_id", "metric", "period", name="uq_usage_counter_period"),
    )


class BillingEvent(Base):
    __tablename__ = "billing_events"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    provider = Column(String(50), default="")
    payload = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

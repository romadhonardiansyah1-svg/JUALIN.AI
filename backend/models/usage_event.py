"""
Usage event ledger for auditable billing metering.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func

from models.database import Base


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    metric = Column(String(100), nullable=False, index=True)
    quantity = Column(Integer, default=1, nullable=False)
    source = Column(String(100), default="", nullable=False)  # e.g. "chat", "inbox_ai", "campaign", "product"
    source_id = Column(String(255), default="")  # e.g. conversation_id, message_id, campaign_id
    idempotency_key = Column(String(255), nullable=False, unique=True, index=True)
    period = Column(String(20), nullable=False, index=True)  # e.g. "2026-06"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

"""
Store trust profile model — refund/shipping policies, support hours, testimonials.
Seller-facing + public-facing trust signals.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.sql import func

from models.database import Base


class StoreTrustProfile(Base):
    __tablename__ = "store_trust_profiles"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)

    # Policies
    refund_policy = Column(Text, default="")
    shipping_policy = Column(Text, default="")
    support_hours = Column(String(255), default="")   # e.g. "Senin-Jumat 09:00-17:00"

    # Trust signals
    verified_phone = Column(Boolean, default=False, nullable=False)
    payment_enabled = Column(Boolean, default=False, nullable=False)

    # Social proof
    testimonials_json = Column(JSON, default=list)  # [{name, text, rating, date}]

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

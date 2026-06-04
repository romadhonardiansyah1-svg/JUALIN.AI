"""
Referral & Reseller system models.
V1: tracking + commission report only; payout manual.
Referral attribution has 30-day expiry window.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, JSON, Boolean, Text
from sqlalchemy.sql import func

from models.database import Base


class ReferralCode(Base):
    __tablename__ = "referral_codes"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False, unique=True, index=True)
    description = Column(String(255), default="")
    commission_percent = Column(Float, default=5.0)  # default 5%
    expiry_days = Column(Integer, default=30)  # attribution window
    is_active = Column(Boolean, default=True, nullable=False)
    total_clicks = Column(Integer, default=0)
    total_conversions = Column(Integer, default=0)
    total_revenue = Column(Float, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ReferralEvent(Base):
    __tablename__ = "referral_events"

    id = Column(Integer, primary_key=True, index=True)
    referral_code_id = Column(Integer, ForeignKey("referral_codes.id"), nullable=False, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    event_type = Column(String(30), nullable=False, index=True)  # click, signup, order, paid
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    order_value = Column(Float, default=0)
    commission_amount = Column(Float, default=0)
    ip_address = Column(String(45), default="")
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ResellerProfile(Base):
    __tablename__ = "reseller_profiles"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), default="")
    phone = Column(String(20), default="")
    referral_code_id = Column(Integer, ForeignKey("referral_codes.id"), nullable=True)
    total_earned = Column(Float, default=0)
    status = Column(String(20), default="active", index=True)  # active, suspended
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CommissionRule(Base):
    __tablename__ = "commission_rules"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    type = Column(String(30), default="percentage")  # percentage, fixed
    value = Column(Float, default=5.0)
    min_order_value = Column(Float, default=0)
    product_category = Column(String(100), default="")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CommissionEvent(Base):
    __tablename__ = "commission_events"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reseller_id = Column(Integer, ForeignKey("reseller_profiles.id"), nullable=True)
    referral_event_id = Column(Integer, ForeignKey("referral_events.id"), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    amount = Column(Float, default=0)
    status = Column(String(20), default="pending", index=True)  # pending, approved, paid
    created_at = Column(DateTime(timezone=True), server_default=func.now())

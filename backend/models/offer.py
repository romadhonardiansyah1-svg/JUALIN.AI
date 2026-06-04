"""
Dynamic Offer Engine models.
AI may recommend offers but seller approval required for broadcast.
One-to-one chat offers allowed if seller rules permit.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, JSON, Boolean, Text
from sqlalchemy.sql import func

from models.database import Base


class Offer(Base):
    __tablename__ = "offers"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    type = Column(String(30), nullable=False, index=True)  # fixed_discount, free_shipping, bundle, urgency
    value = Column(Float, default=0)  # discount amount or percent
    value_type = Column(String(20), default="fixed")  # fixed, percent
    min_order_value = Column(Float, default=0)
    product_ids_json = Column(JSON, default=list)  # applicable product IDs
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    max_redemptions = Column(Integer, default=0)  # 0 = unlimited
    current_redemptions = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, nullable=False)
    allow_chat_auto = Column(Boolean, default=False)  # allow AI to suggest in 1:1 chat
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class OfferRecommendation(Base):
    __tablename__ = "offer_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    offer_id = Column(Integer, ForeignKey("offers.id"), nullable=True)
    trigger_type = Column(String(50), nullable=False)  # cart_abandon, repeat_buyer, low_stock, etc.
    customer_segment = Column(String(100), default="all")
    estimated_impact = Column(Float, default=0)
    status = Column(String(20), default="pending", index=True)  # pending, approved, dismissed
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OfferRedemption(Base):
    __tablename__ = "offer_redemptions"

    id = Column(Integer, primary_key=True, index=True)
    offer_id = Column(Integer, ForeignKey("offers.id"), nullable=False, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    discount_applied = Column(Float, default=0)
    channel = Column(String(30), default="chat")  # chat, campaign, storefront
    created_at = Column(DateTime(timezone=True), server_default=func.now())

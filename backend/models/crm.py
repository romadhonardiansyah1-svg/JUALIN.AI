"""
Formal CRM models built on top of lightweight customer memory.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Float, UniqueConstraint
from sqlalchemy.sql import func

from models.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    memory_id = Column(Integer, ForeignKey("customer_memories.id"), nullable=True, index=True)
    name = Column(String(255), default="Customer")
    phone = Column(String(50), default="", index=True)
    email = Column(String(255), default="", index=True)
    whatsapp_id = Column(String(255), default="", index=True)
    session_id = Column(String(255), default="", index=True)
    tags = Column(JSON, default=list)
    total_orders = Column(Integer, default=0)
    total_spent = Column(Float, default=0)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("seller_id", "phone", name="uq_customer_phone_per_seller"),
    )


class CustomerProfile(Base):
    __tablename__ = "customer_profiles"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, unique=True, index=True)
    preferences = Column(JSON, default=list)
    budget_range = Column(String(100), default="")
    sizes = Column(JSON, default=list)
    address_book = Column(JSON, default=list)
    notes = Column(Text, default="")
    sentiment = Column(String(20), default="neutral")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CustomerEvent(Base):
    __tablename__ = "customer_events"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    title = Column(String(255), default="")
    data = Column(JSON, default=dict)
    source = Column(String(50), default="system")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CustomerTag(Base):
    __tablename__ = "customer_tags"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    color = Column(String(20), default="#22C55E")
    description = Column(String(255), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("seller_id", "name", name="uq_customer_tag_name_per_seller"),
    )

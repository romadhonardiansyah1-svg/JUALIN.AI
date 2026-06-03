"""
JUALIN.AI — Order Model
Orders created by AI agent from chat conversations
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Enum as SAEnum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from models.database import Base


class OrderStatus(str, enum.Enum):
    PENDING = "pending"        # Order dibuat, belum bayar
    PAID = "paid"              # Sudah bayar
    SHIPPED = "shipped"        # Sudah dikirim
    DONE = "done"              # Selesai
    CANCELLED = "cancelled"    # Dibatalkan


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)
    
    # Customer info
    customer_name = Column(String(255), nullable=False)
    customer_phone = Column(String(20), default="")
    customer_address = Column(Text, default="")
    
    # Order details
    items = Column(JSON, nullable=False)  # [{"product_id": 1, "nama": "Baju Pink", "qty": 2, "harga": 89000}]
    total = Column(Float, nullable=False)
    
    # Status
    status = Column(SAEnum(OrderStatus), default=OrderStatus.PENDING, nullable=False)
    notes = Column(Text, default="")
    
    # Follow-up tracking
    followup_count = Column(Integer, default=0)
    last_followup_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    seller = relationship("User", back_populates="orders")
    conversation = relationship("Conversation", back_populates="orders")

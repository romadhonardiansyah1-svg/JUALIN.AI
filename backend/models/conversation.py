"""
JUALIN.AI — Conversation & Message Models
Chat history storage for AI context and seller monitoring
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from models.database import Base


class MessageRole(str, enum.Enum):
    CUSTOMER = "customer"
    AI = "ai"
    SYSTEM = "system"


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Customer info
    session_id = Column(String(100), nullable=False, index=True)  # Unique per customer session
    customer_name = Column(String(255), default="Customer")
    customer_phone = Column(String(20), default="")
    
    # Status
    is_active = Column(Integer, default=1)
    is_urgent = Column(Integer, default=0)  # Flagged by guardrail for escalation
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    seller = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan",
                           order_by="Message.created_at")
    orders = relationship("Order", back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    
    role = Column(SAEnum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    
    # Metadata
    tokens_used = Column(Integer, default=0)  # Track token usage per message
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")

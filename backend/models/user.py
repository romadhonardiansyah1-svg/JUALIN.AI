"""
JUALIN.AI — User Model (Seller)
Multi-tenant: each seller has their own store with isolated data
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from models.database import Base


class UserTier(str, enum.Enum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    BISNIS = "bisnis"


class UserRole(str, enum.Enum):
    SELLER = "seller"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    
    # Store info
    nama_toko = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    deskripsi_toko = Column(String(1000), default="")
    no_hp = Column(String(20), default="")
    
    # Subscription
    tier = Column(SAEnum(UserTier), default=UserTier.FREE, nullable=False)
    role = Column(SAEnum(UserRole), default=UserRole.SELLER, nullable=False)
    
    # AI Settings
    ai_active = Column(Boolean, default=True)
    ai_style = Column(String(20), default="santai")  # formal/santai/gaul
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    products = relationship("Product", back_populates="seller", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="seller", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="seller", cascade="all, delete-orphan")

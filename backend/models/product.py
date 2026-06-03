"""
JUALIN.AI — Product Model
With pgvector embedding for semantic search
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from models.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Product info
    nama = Column(String(255), nullable=False)
    deskripsi = Column(Text, default="")
    harga = Column(Float, nullable=False)
    stok = Column(Integer, default=0)
    kategori = Column(String(100), default="umum")
    foto_url = Column(String(500), default="")
    
    # AI-generated content
    summary = Column(Text, default="")  # Pre-computed summary for AI context
    
    # Semantic search vector (384 dimensions for all-MiniLM-L6-v2)
    embedding = Column(Vector(384), nullable=True)
    
    # Status
    is_active = Column(Integer, default=1)  # 1 = active, 0 = archived
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    seller = relationship("User", back_populates="products")

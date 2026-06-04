"""
AI Storefront builder models.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.sql import func

from models.database import Base


class Storefront(Base):
    __tablename__ = "storefronts"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    title = Column(String(255), default="")
    tagline = Column(String(500), default="")
    theme_json = Column(JSON, default=dict)  # colors, fonts, layout
    is_published = Column(Boolean, default=False, nullable=False)
    seo_title = Column(String(255), default="")
    seo_description = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class StorefrontSection(Base):
    __tablename__ = "storefront_sections"

    id = Column(Integer, primary_key=True, index=True)
    storefront_id = Column(Integer, ForeignKey("storefronts.id"), nullable=False, index=True)
    type = Column(String(50), nullable=False)  # hero, categories, featured_products, testimonials, cta
    title = Column(String(255), default="")
    content_json = Column(JSON, default=dict)
    order_index = Column(Integer, default=0)
    is_visible = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

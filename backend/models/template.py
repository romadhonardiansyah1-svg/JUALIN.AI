"""
Template marketplace models — internal curated templates v1.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.sql import func

from models.database import Base


class Template(Base):
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(50), nullable=False, index=True)  # campaign, workflow, prompt, storefront_section, canned_reply
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    category = Column(String(100), default="general", index=True)
    niche = Column(String(50), nullable=True, index=True)    # kuliner, fashion, skincare, etc.
    pack_id = Column(String(50), nullable=True, index=True)  # groups templates in a pack
    content_json = Column(JSON, default=dict)
    tags = Column(JSON, default=list)
    is_public = Column(Boolean, default=True, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

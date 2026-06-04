"""
Concierge checklist model — admin-assisted setup for UMKM sellers.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.sql import func

from models.database import Base


class ConciergeChecklist(Base):
    __tablename__ = "concierge_checklists"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Checklist items
    products_imported = Column(Boolean, default=False, nullable=False)
    whatsapp_connected = Column(Boolean, default=False, nullable=False)
    payment_connected = Column(Boolean, default=False, nullable=False)
    storefront_published = Column(Boolean, default=False, nullable=False)
    first_campaign_draft = Column(Boolean, default=False, nullable=False)

    notes = Column(Text, default="")

    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

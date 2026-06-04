"""
Growth link model — trackable links for WhatsApp, storefront, campaigns.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, JSON, Boolean
from sqlalchemy.sql import func

from models.database import Base


class GrowthLink(Base):
    __tablename__ = "growth_links"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False, unique=True, index=True)
    source = Column(String(50), default="manual", index=True)  # wa_link, storefront_cta, campaign, click_to_whatsapp_ads, manual
    campaign_name = Column(String(255), default="")
    target_url = Column(String(500), default="")
    click_count = Column(Integer, default=0)
    order_count = Column(Integer, default=0)
    revenue = Column(Float, default=0)
    metadata_json = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

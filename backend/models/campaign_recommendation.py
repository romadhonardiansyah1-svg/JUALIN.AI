"""
AI Campaign autopilot recommendation model.
Recommendations are suggestions only — seller must approve before sending.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.sql import func

from models.database import Base


class CampaignRecommendation(Base):
    __tablename__ = "campaign_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    trigger_type = Column(String(100), nullable=False, index=True)  # abandoned_payment, inactive_customers, repeat_buyer, overstock, new_product
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    suggested_content = Column(Text, default="")
    target_audience_json = Column(JSON, default=dict)  # {filter criteria}
    estimated_reach = Column(Integer, default=0)
    status = Column(String(20), default="pending", index=True)  # pending, draft_created, dismissed
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True)  # linked draft
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

"""
Campaign generator and broadcast approval models.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.sql import func

from models.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    segment = Column(String(100), default="all")
    channel = Column(String(50), default="whatsapp")
    content = Column(Text, default="")
    status = Column(String(20), default="draft", index=True)
    generated_by = Column(String(50), default="ai")
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    name = Column(String(255), default="")
    phone = Column(String(50), default="")
    status = Column(String(20), default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CampaignMessage(Base):
    __tablename__ = "campaign_messages"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    recipient_id = Column(Integer, ForeignKey("campaign_recipients.id"), nullable=True, index=True)
    status = Column(String(20), default="queued")
    content = Column(Text, default="")
    provider_message_id = Column(String(255), default="")
    error_message = Column(Text, default="")
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

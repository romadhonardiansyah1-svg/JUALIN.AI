"""
WhatsApp message template model — for campaigns outside 24h service window.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.sql import func

from models.database import Base


class WhatsAppMessageTemplate(Base):
    __tablename__ = "whatsapp_message_templates"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(50), default="utility")   # utility, marketing
    language = Column(String(10), default="id")
    body = Column(Text, default="")
    variables_json = Column(JSON, default=list)  # [{key, sample_value}]
    status = Column(String(30), default="draft", index=True)  # draft, pending_review, approved, rejected
    provider_template_id = Column(String(255), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

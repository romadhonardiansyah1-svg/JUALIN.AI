"""
Lead capture system models.
Public form rate limited and spam protected.
Submission creates customer/lead event in CRM.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Boolean, Text
from sqlalchemy.sql import func

from models.database import Base


class LeadForm(Base):
    __tablename__ = "lead_forms"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    fields_json = Column(JSON, default=list)  # [{name, type, label, required}]
    success_message = Column(String(500), default="Terima kasih! Kami akan segera menghubungi Anda.")
    is_active = Column(Boolean, default=True, nullable=False)
    submission_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class LeadSubmission(Base):
    __tablename__ = "lead_submissions"

    id = Column(Integer, primary_key=True, index=True)
    form_id = Column(Integer, ForeignKey("lead_forms.id"), nullable=False, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    data_json = Column(JSON, default=dict)  # submitted field values
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    source_ip = Column(String(45), default="")
    status = Column(String(20), default="new", index=True)  # new, contacted, converted, spam
    created_at = Column(DateTime(timezone=True), server_default=func.now())

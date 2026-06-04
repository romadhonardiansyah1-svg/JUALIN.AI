"""
Sales Playbook Engine models.
Playbook v1 curated: first-time, price-sensitive, repeat, abandoned, complaint, education.
AI prompt receives selected_playbook. Seller can enable/disable but not run arbitrary code.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Boolean, Text
from sqlalchemy.sql import func

from models.database import Base


class SalesPlaybook(Base):
    __tablename__ = "sales_playbooks"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    key = Column(String(50), nullable=False, index=True)  # first_time_buyer, price_sensitive, etc.
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    prompt_instructions = Column(Text, default="")  # extra system prompt for AI
    tone = Column(String(50), default="friendly")  # friendly, professional, casual
    is_enabled = Column(Boolean, default=True, nullable=False)
    priority = Column(Integer, default=0)  # higher = checked first
    trigger_conditions_json = Column(JSON, default=dict)  # {customer_tags, order_count_min, etc.}
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class SalesPlaybookRule(Base):
    __tablename__ = "sales_playbook_rules"

    id = Column(Integer, primary_key=True, index=True)
    playbook_id = Column(Integer, ForeignKey("sales_playbooks.id"), nullable=False, index=True)
    condition_type = Column(String(50), nullable=False)  # customer_tag, order_count, last_order_days, etc.
    operator = Column(String(20), default="eq")  # eq, gt, lt, gte, lte, contains
    value = Column(String(255), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

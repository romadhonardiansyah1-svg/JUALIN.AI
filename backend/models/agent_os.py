"""
JUALIN OS — Multi-Agent Business OS core models.

Tabel:
- agent_policies     : konfigurasi otonomi & guardrail per seller (1 baris / seller)
- agent_runs         : log aktivitas — 1 baris per aktivasi agen (the "activity feed")
- agent_approvals    : antrean human-in-the-loop untuk aksi berisiko
- negotiation_states : state tawar-menawar per percakapan
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, JSON, Float, Boolean, UniqueConstraint,
)
from sqlalchemy.sql import func

from models.database import Base

# Peran agen yang dikenal di seluruh OS
AGENT_ROLES = ("orchestrator", "sales", "negotiator", "inventory", "growth", "finance", "cs")


class AgentPolicy(Base):
    __tablename__ = "agent_policies"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Tingkat otonomi: assist | auto_with_approval | full_auto
    autonomy_level = Column(String(30), default="auto_with_approval", nullable=False)

    # Sakelar per-agen
    allow_auto_negotiation = Column(Boolean, default=True, nullable=False)
    allow_auto_followup = Column(Boolean, default=True, nullable=False)
    allow_low_stock_alert = Column(Boolean, default=True, nullable=False)
    daily_brief_enabled = Column(Boolean, default=True, nullable=False)

    # Guardrail negosiasi (persen)
    max_discount_percent = Column(Float, default=15.0, nullable=False)
    margin_floor_percent = Column(Float, default=10.0, nullable=False)
    require_approval_above_percent = Column(Float, default=10.0, nullable=False)
    nego_max_rounds = Column(Integer, default=3, nullable=False)

    # Inventory
    low_stock_threshold = Column(Integer, default=3, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("seller_id", name="uq_agent_policy_seller"),
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    agent_role = Column(String(30), nullable=False, index=True)
    trigger = Column(String(30), default="chat", nullable=False)   # chat|cron|payment|manual
    status = Column(String(20), default="done", nullable=False)    # done|escalated|blocked|failed|needs_approval
    summary = Column(String(500), default="")
    detail_json = Column(JSON, default=dict)

    conversation_id = Column(Integer, nullable=True, index=True)
    customer_id = Column(Integer, nullable=True, index=True)
    order_id = Column(Integer, nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class AgentApproval(Base):
    __tablename__ = "agent_approvals"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    agent_role = Column(String(30), default="negotiator", nullable=False)
    action_type = Column(String(50), nullable=False, index=True)   # apply_discount|refund|broadcast|large_order
    title = Column(String(255), default="")
    detail_json = Column(JSON, default=dict)
    status = Column(String(20), default="pending", nullable=False, index=True)  # pending|approved|rejected|expired
    reason = Column(String(500), default="")
    decided_by = Column(Integer, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)

    conversation_id = Column(Integer, nullable=True, index=True)
    order_id = Column(Integer, nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class NegotiationState(Base):
    __tablename__ = "negotiation_states"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(Integer, nullable=False, index=True)
    product_id = Column(Integer, nullable=True, index=True)

    list_price = Column(Float, default=0)
    floor_price = Column(Float, default=0)
    current_offer = Column(Float, default=0)
    last_customer_ask = Column(Float, default=0)
    rounds = Column(Integer, default=0)
    status = Column(String(20), default="active", nullable=False)  # active|accepted|rejected|escalated
    history_json = Column(JSON, default=list)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

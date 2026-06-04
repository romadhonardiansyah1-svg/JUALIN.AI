"""
Template-based UMKM workflow automation models.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.sql import func

from models.database import Base


class AutomationRule(Base):
    __tablename__ = "automation_rules"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    template_key = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    status = Column(String(20), default="active", index=True)
    trigger_json = Column(JSON, default=dict)
    action_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AutomationRun(Base):
    __tablename__ = "automation_runs"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    rule_id = Column(Integer, ForeignKey("automation_rules.id"), nullable=True, index=True)
    idempotency_key = Column(String(255), nullable=False, unique=True, index=True)
    status = Column(String(20), default="running")
    context_json = Column(JSON, default=dict)
    error_message = Column(Text, default="")
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)


class AutomationRunStep(Base):
    __tablename__ = "automation_run_steps"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("automation_runs.id"), nullable=False, index=True)
    step_type = Column(String(100), nullable=False)
    status = Column(String(20), default="ok")
    input_json = Column(JSON, default=dict)
    output_json = Column(JSON, default=dict)
    error_message = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

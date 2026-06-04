"""
Experimentation System models.
V1: prompt variant, campaign CTA, storefront CTA, offer wording.
Assignment deterministic per customer/session. No auto-winner.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Boolean, Text, Float
from sqlalchemy.sql import func

from models.database import Base


class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    type = Column(String(50), nullable=False, index=True)  # prompt, campaign_cta, storefront_cta, offer_wording
    status = Column(String(20), default="draft", index=True)  # draft, running, stopped, completed
    started_at = Column(DateTime(timezone=True), nullable=True)
    stopped_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ExperimentVariant(Base):
    __tablename__ = "experiment_variants"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # A, B, control
    content = Column(Text, default="")
    weight = Column(Integer, default=50)  # traffic weight percentage
    impressions = Column(Integer, default=0)
    conversions = Column(Integer, default=0)
    revenue = Column(Float, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ExperimentAssignment(Base):
    __tablename__ = "experiment_assignments"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("experiment_variants.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    session_id = Column(String(100), default="", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ExperimentEvent(Base):
    __tablename__ = "experiment_events"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("experiment_variants.id"), nullable=False, index=True)
    assignment_id = Column(Integer, ForeignKey("experiment_assignments.id"), nullable=True)
    event_type = Column(String(50), nullable=False, index=True)  # impression, click, conversion, revenue
    value = Column(Float, default=0)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

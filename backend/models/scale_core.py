"""
Core production tables for scale-up modules.
"""
import uuid
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, UniqueConstraint, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from models.database import Base


class IntegrationAccount(Base):
    __tablename__ = "integration_accounts"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider_type = Column(String(50), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)
    status = Column(String(20), default="inactive", nullable=False)
    display_name = Column(String(255), default="")
    config_encrypted = Column(Text, default="")
    capabilities = Column(JSON, default=list)
    last_health_status = Column(String(20), default="unknown")
    last_health_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("seller_id", "provider_type", "provider", name="uq_integration_account_provider"),
    )


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), nullable=False, index=True)
    event_type = Column(String(100), default="", index=True)
    idempotency_key = Column(String(255), nullable=False, unique=True, index=True)
    external_event_id = Column(String(255), default="", index=True)
    status = Column(String(20), default="received", nullable=False)
    payload = Column(JSON, default=dict)
    error_message = Column(Text, default="")
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # P1.1: tenant and account mapping for durable inbox
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    provider_account_id = Column(String(255), nullable=True, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=True, index=True)


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    job_type = Column(String(100), nullable=False, index=True)
    idempotency_key = Column(String(255), nullable=False, unique=True, index=True)
    status = Column(String(20), default="queued", nullable=False)  # queued|running|done|failed|dead_letter|skipped
    payload = Column(JSON, default=dict)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    # P1.1: retryable default false for safety (was true)
    retryable = Column(Boolean, default=False, nullable=False, server_default="false")
    error_message = Column(Text, default="")
    last_error_code = Column(String(50), default="")
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    locked_by = Column(String(100), default="")
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # ── P1.1 safety foundation — lease/fencing fields ──
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    claim_token = Column(UUID(as_uuid=True), nullable=True)
    lock_version = Column(Integer, nullable=False, default=0, server_default="0")
    execution_stage = Column(String(30), nullable=False, default="unknown", server_default="unknown")
    side_effect_started_at = Column(DateTime(timezone=True), nullable=True)
    payload_digest = Column(String(64), nullable=True)
    handler_contract_version = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_jobs_status_next_run", "status", "next_run_at"),
        Index("ix_jobs_processable", "status", "execution_stage", "next_run_at", "lease_expires_at"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    actor_type = Column(String(50), default="system", nullable=False)
    action = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(100), nullable=False, index=True)
    entity_id = Column(String(100), default="", index=True)
    before = Column(JSON, default=dict)
    after = Column(JSON, default=dict)
    metadata_json = Column(JSON, default=dict)
    request_id = Column(String(100), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

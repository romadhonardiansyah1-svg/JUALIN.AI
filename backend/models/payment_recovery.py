"""
Payment recovery domain — P2.1 foundation for consent, opportunity, dispatch, outcome.
"""
import uuid
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Boolean, Numeric,
    UniqueConstraint, Index, CheckConstraint, JSON, LargeBinary, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from models.database import Base


class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    provider = Column(String(50), nullable=False)
    provider_account_id = Column(String(100), nullable=True, index=True)
    external_attempt_id = Column(String(255), nullable=True, index=True)
    attempt_version = Column(Integer, nullable=False)
    is_current = Column(Boolean, nullable=False, default=True, server_default="true")
    status = Column(String(30), nullable=False, default="pending", server_default="pending")
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="IDR", server_default="IDR")
    payment_expires_at = Column(DateTime(timezone=True), nullable=True)
    trusted_link_reference = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("seller_id", "order_id", "attempt_version", name="uq_payment_attempt_seller_order_version"),
        UniqueConstraint(
            "provider", "provider_account_id", "external_attempt_id",
            name="uq_payment_attempt_provider_account_external",
        ),
        Index("ix_payment_attempt_current", "seller_id", "order_id", "is_current"),
        CheckConstraint("attempt_version >= 1", name="ck_payment_attempt_version_positive"),
        CheckConstraint("amount >= 0", name="ck_payment_attempt_amount_non_negative"),
    )


class PaymentRecoveryControl(Base):
    """Global kill switch / control singleton (P2.3)."""
    __tablename__ = "payment_recovery_controls"

    id = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    paused = Column(Boolean, nullable=False, default=True, server_default="true")
    version = Column(Integer, nullable=False, default=1, server_default="1")
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    reason = Column(String(500), default="")


class ContactSubject(Base):
    """Stable tenant contact identity, not plaintext phone."""
    __tablename__ = "contact_subjects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    channel = Column(String(20), nullable=False, default="whatsapp", server_default="whatsapp")
    address_ciphertext = Column(LargeBinary, nullable=True)
    address_key_version = Column(Integer, nullable=True)
    address_revision = Column(Integer, nullable=False, default=1, server_default="1")
    status = Column(String(20), nullable=False, default="active", server_default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_contact_subject_seller_channel", "seller_id", "channel"),
    )


class ContactSubjectFingerprint(Base):
    __tablename__ = "contact_subject_fingerprints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    contact_subject_id = Column(UUID(as_uuid=True), ForeignKey("contact_subjects.id"), nullable=False, index=True)
    channel = Column(String(20), nullable=False, default="whatsapp")
    key_version = Column(Integer, nullable=False)
    fingerprint = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    retired_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("seller_id", "channel", "key_version", "fingerprint", name="uq_contact_fingerprint"),
    )


class ContactPermission(Base):
    """History ledger for consent, exact order/payment-cycle scope."""
    __tablename__ = "contact_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    contact_subject_id = Column(UUID(as_uuid=True), ForeignKey("contact_subjects.id"), nullable=False, index=True)
    channel = Column(String(20), nullable=False, default="whatsapp")
    address_ciphertext = Column(LargeBinary, nullable=True)
    address_key_version = Column(Integer, nullable=True)
    address_fingerprint = Column(String(255), nullable=False, index=True)
    fingerprint_key_version = Column(Integer, nullable=False, default=1)
    purpose = Column(String(50), nullable=False, default="transactional_payment_reminder")
    scope_type = Column(String(30), nullable=False, default="order_payment_cycle")
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    payment_attempt_id = Column(UUID(as_uuid=True), ForeignKey("payment_attempts.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="active", server_default="active")
    provenance = Column(String(50), nullable=False)
    source_reference = Column(String(255), nullable=True)
    granted_at = Column(DateTime(timezone=True), server_default=func.now())
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "uq_contact_permission_active",
            "seller_id", "channel", "contact_subject_id", "purpose", "scope_type", "payment_attempt_id",
            unique=True,
            postgresql_where=text("status='active'"),
        ),
    )


class ContactSuppression(Base):
    """Recipient-level STOP/Berhenti suppression that beats order-scoped grants."""
    __tablename__ = "contact_suppressions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    channel = Column(String(20), nullable=False, default="whatsapp")
    contact_subject_id = Column(UUID(as_uuid=True), ForeignKey("contact_subjects.id"), nullable=False, index=True)
    address_fingerprint = Column(String(255), nullable=False, index=True)
    fingerprint_key_version = Column(Integer, nullable=False, default=1)
    purpose = Column(String(50), nullable=False, default="transactional_payment_reminder")
    status = Column(String(20), nullable=False, default="active", server_default="active")
    source_event = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    lifted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "uq_contact_suppression_active",
            "seller_id", "channel", "contact_subject_id", "purpose",
            unique=True,
            postgresql_where=text("status='active'"),
        ),
    )


class RevenueOpportunity(Base):
    __tablename__ = "revenue_opportunities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    payment_attempt_id = Column(UUID(as_uuid=True), ForeignKey("payment_attempts.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    opportunity_type = Column(String(50), nullable=False, default="pending_payment_recovery")
    status = Column(String(30), nullable=False, default="detected", server_default="detected", index=True)
    signal_key = Column(String(255), nullable=False, unique=True)
    amount_snapshot = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="IDR", server_default="IDR")
    evidence_json = Column(JSON, default=dict)
    policy_version = Column(Integer, nullable=False, default=1)
    state_version = Column(Integer, nullable=False, default=1, server_default="1")
    eligible_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    suppression_code = Column(String(50), nullable=True)
    terminal_reason_code = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("amount_snapshot >= 0", name="ck_opportunity_amount_non_negative"),
    )


class OutboundDispatch(Base):
    __tablename__ = "outbound_dispatches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    opportunity_id = Column(UUID(as_uuid=True), ForeignKey("revenue_opportunities.id"), nullable=False, index=True)
    approval_id = Column(Integer, ForeignKey("agent_approvals.id"), nullable=True, index=True)
    background_job_id = Column(Integer, ForeignKey("background_jobs.id"), nullable=True, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=True, index=True)
    channel_type = Column(String(20), nullable=False, default="whatsapp")
    status = Column(String(30), nullable=False, default="pending", server_default="pending", index=True)
    delivery_status = Column(String(20), nullable=False, default="not_available", server_default="not_available")
    template_code = Column(String(100), nullable=False)
    template_params_json = Column(JSON, default=dict)
    action_digest = Column(String(64), nullable=False)
    contact_permission_id = Column(UUID(as_uuid=True), ForeignKey("contact_permissions.id"), nullable=False, index=True)
    contact_subject_id = Column(UUID(as_uuid=True), ForeignKey("contact_subjects.id"), nullable=False, index=True)
    recipient_fingerprint = Column(String(255), nullable=False)
    idempotency_key = Column(String(255), nullable=False, unique=True)
    provider = Column(String(50), nullable=False, default="whatsapp_cloud")
    provider_request_id = Column(String(255), nullable=True, index=True)
    provider_message_id = Column(String(255), nullable=True, index=True)
    attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_error_code = Column(String(100), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    delivery_failed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("opportunity_id", name="uq_dispatch_opportunity"),
        Index("ix_dispatch_provider_message", "provider", "channel_id", "provider_message_id"),
    )


class OutcomeEvent(Base):
    __tablename__ = "outcome_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    payment_attempt_id = Column(UUID(as_uuid=True), ForeignKey("payment_attempts.id"), nullable=False, index=True)
    opportunity_id = Column(UUID(as_uuid=True), ForeignKey("revenue_opportunities.id"), nullable=False, index=True)
    dispatch_id = Column(UUID(as_uuid=True), ForeignKey("outbound_dispatches.id"), nullable=True, index=True)
    event_type = Column(String(30), nullable=False)  # payment_observed, payment_reversed, etc
    source_event_key = Column(String(255), nullable=False, unique=True)
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="IDR")
    reversal_of_id = Column(UUID(as_uuid=True), ForeignKey("outcome_events.id"), nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    evidence_json = Column(JSON, default=dict)


class AttributionAssessment(Base):
    __tablename__ = "attribution_assessments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    outcome_event_id = Column(UUID(as_uuid=True), ForeignKey("outcome_events.id"), nullable=False, index=True)
    method = Column(String(30), nullable=False)  # rule_attributed, experiment_causal
    rule_version = Column(String(50), nullable=True)
    experiment_id = Column(String(100), nullable=True)
    assessed_at = Column(DateTime(timezone=True), server_default=func.now())
    window_start = Column(DateTime(timezone=True), nullable=True)
    window_end = Column(DateTime(timezone=True), nullable=True)
    estimate = Column(Numeric(18, 2), nullable=True)
    confidence = Column(String(50), nullable=True)
    evidence_json = Column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("outcome_event_id", "method", "rule_version", name="uq_attribution_outcome_method_rule"),
    )


class RecipientContactWindow(Base):
    __tablename__ = "recipient_contact_windows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    contact_subject_id = Column(UUID(as_uuid=True), ForeignKey("contact_subjects.id"), nullable=False, index=True)
    purpose = Column(String(50), nullable=False, default="transactional_payment_reminder")
    opportunity_id = Column(UUID(as_uuid=True), ForeignKey("revenue_opportunities.id"), nullable=False, index=True)
    dispatch_id = Column(UUID(as_uuid=True), ForeignKey("outbound_dispatches.id"), nullable=True, index=True)
    window_started_at = Column(DateTime(timezone=True), nullable=False)
    window_ends_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), nullable=False, default="reserved", server_default="reserved")
    reserved_at = Column(DateTime(timezone=True), server_default=func.now())
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    released_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    release_reason = Column(String(50), nullable=True)

    __table_args__ = (
        Index("ix_contact_window_seller_subject_purpose", "seller_id", "contact_subject_id", "purpose"),
    )

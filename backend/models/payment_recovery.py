"""
Payment recovery safety foundation — PaymentAttempt as immutable payment-cycle source (P1.1/P2.1)
"""
import uuid
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Numeric, UniqueConstraint, Index, CheckConstraint
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
        # Partial unique for exactly one current attempt per seller/order will be handled via partial index in migration
        Index("ix_payment_attempt_current", "seller_id", "order_id", "is_current"),
        CheckConstraint("attempt_version >= 1", name="ck_payment_attempt_version_positive"),
        CheckConstraint("amount >= 0", name="ck_payment_attempt_amount_non_negative"),
    )

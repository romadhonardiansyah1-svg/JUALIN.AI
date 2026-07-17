"""
P3.1 — Rotating browser sessions (AuthSession) for HttpOnly cookie migration.
"""
import uuid
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from models.database import Base


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    family_id = Column(UUID(as_uuid=True), nullable=False, index=True, default=uuid.uuid4)
    rotation_counter = Column(Integer, nullable=False, default=0)
    is_current = Column(Boolean, nullable=False, default=True, server_default="true")
    refresh_token_hash = Column(String(64), nullable=False, unique=True, index=True)
    csrf_token_hash = Column(String(64), nullable=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    effective_seller_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    auth_mode = Column(String(20), nullable=False, default="password", server_default="password")
    impersonation_id = Column(Integer, nullable=True)
    scopes = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    absolute_expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_reason = Column(String(100), nullable=True)
    ip_hash = Column(String(64), nullable=True)
    user_agent_hash = Column(String(64), nullable=True)

    __table_args__ = (
        Index(
            "uq_auth_sessions_current_family",
            "family_id",
            unique=True,
            postgresql_where=text("is_current = true AND revoked_at IS NULL"),
        ),
    )

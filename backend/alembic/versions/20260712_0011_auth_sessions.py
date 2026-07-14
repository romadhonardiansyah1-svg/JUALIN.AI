"""P3.1 — Rotating browser sessions for HttpOnly cookie migration"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260712_0011"
down_revision = "20260712_0010"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    conn = op.get_bind()
    try:
        inspector = sa.inspect(conn)
        return inspector.has_table(table)
    except Exception:
        return False


def upgrade():
    if not _has_table("auth_sessions"):
        op.create_table(
            "auth_sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("rotation_counter", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
            sa.Column("csrf_token_hash", sa.String(length=64), nullable=True),
            sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("effective_seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("auth_mode", sa.String(length=20), nullable=False, server_default="password"),
            sa.Column("impersonation_id", sa.Integer(), nullable=True),
            sa.Column("scopes", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("last_used_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_reason", sa.String(length=100), nullable=True),
            sa.Column("ip_hash", sa.String(length=64), nullable=True),
            sa.Column("user_agent_hash", sa.String(length=64), nullable=True),
        )
        op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
        op.create_index("ix_auth_sessions_seller_id", "auth_sessions", ["seller_id"])
        op.create_index("ix_auth_sessions_family_id", "auth_sessions", ["family_id"])
        op.create_index("ix_auth_sessions_refresh_token_hash", "auth_sessions", ["refresh_token_hash"], unique=True)
        op.create_index("ix_auth_sessions_actor_user_id", "auth_sessions", ["actor_user_id"])


def downgrade():
    if _has_table("auth_sessions"):
        op.drop_index("ix_auth_sessions_actor_user_id", table_name="auth_sessions")
        op.drop_index("ix_auth_sessions_refresh_token_hash", table_name="auth_sessions")
        op.drop_index("ix_auth_sessions_family_id", table_name="auth_sessions")
        op.drop_index("ix_auth_sessions_seller_id", table_name="auth_sessions")
        op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
        op.drop_table("auth_sessions")

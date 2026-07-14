"""P2.4 — Public payment capability HMAC + session (secure token transition)"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260712_0010"
down_revision = "20260712_0009"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    conn = op.get_bind()
    try:
        inspector = sa.inspect(conn)
        return inspector.has_table(table)
    except Exception:
        return False


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    try:
        inspector = sa.inspect(conn)
        cols = [c["name"] for c in inspector.get_columns(table)]
        return column in cols
    except Exception:
        return False


def _has_index(table: str, index_name: str) -> bool:
    conn = op.get_bind()
    try:
        inspector = sa.inspect(conn)
        indexes = [idx["name"] for idx in inspector.get_indexes(table)]
        return index_name in indexes
    except Exception:
        return False


def upgrade():
    # ── payment_capabilities — HMAC stored, not plaintext ──
    if not _has_table("payment_capabilities"):
        op.create_table(
            "payment_capabilities",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
            sa.Column("payment_attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payment_attempts.id"), nullable=False),
            sa.Column("token_hmac", sa.String(length=64), nullable=False),
            sa.Column("key_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("audience", sa.String(length=50), nullable=False, server_default="public_payment"),
            sa.Column("purpose", sa.String(length=50), nullable=False, server_default="payment_status"),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revocation_epoch", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_legacy_query_token", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        )
        op.create_index("ix_payment_capabilities_seller_id", "payment_capabilities", ["seller_id"])
        op.create_index("ix_payment_capabilities_order_id", "payment_capabilities", ["order_id"])
        op.create_index("ix_payment_capabilities_payment_attempt_id", "payment_capabilities", ["payment_attempt_id"])
        op.create_unique_constraint("uq_payment_capabilities_token_hmac", "payment_capabilities", ["token_hmac"])
        op.create_index("ix_payment_capabilities_token_hmac", "payment_capabilities", ["token_hmac"])

    # ── payment_capability_sessions — short-lived HttpOnly session from fragment exchange ──
    if not _has_table("payment_capability_sessions"):
        op.create_table(
            "payment_capability_sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("capability_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payment_capabilities.id"), nullable=True),
            sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
            sa.Column("payment_attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payment_attempts.id"), nullable=False),
            sa.Column("session_token_hmac", sa.String(length=64), nullable=False),
            sa.Column("key_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("audience", sa.String(length=50), nullable=False, server_default="public_payment_session"),
            sa.Column("purpose", sa.String(length=50), nullable=False, server_default="payment_status"),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        )
        op.create_index("ix_payment_capability_sessions_seller_id", "payment_capability_sessions", ["seller_id"])
        op.create_index("ix_payment_capability_sessions_order_id", "payment_capability_sessions", ["order_id"])
        op.create_unique_constraint("uq_payment_capability_sessions_token_hmac", "payment_capability_sessions", ["session_token_hmac"])
        op.create_index("ix_payment_capability_sessions_token_hmac", "payment_capability_sessions", ["session_token_hmac"])

    # ── orders: add HMAC column for transition from plaintext payment_access_token ──
    if not _has_column("orders", "payment_access_token_hmac"):
        op.add_column("orders", sa.Column("payment_access_token_hmac", sa.String(length=64), nullable=True))
    if not _has_column("orders", "payment_access_token_key_version"):
        op.add_column("orders", sa.Column("payment_access_token_key_version", sa.Integer(), nullable=True))
    if not _has_column("orders", "payment_access_token_expires_at"):
        op.add_column("orders", sa.Column("payment_access_token_expires_at", sa.DateTime(timezone=True), nullable=True))

    if not _has_index("orders", "ix_orders_payment_access_token_hmac"):
        op.create_index("ix_orders_payment_access_token_hmac", "orders", ["payment_access_token_hmac"])

    # ── Legacy plaintext token backfill note: do NOT automatically backfill all old tokens to HMAC in this migration
    # for safety. Backfill will be done via reviewed key-aware job with dual-read.
    # New writes must not fill plaintext column — enforced at application layer.


def downgrade():
    if _has_index("orders", "ix_orders_payment_access_token_hmac"):
        op.drop_index("ix_orders_payment_access_token_hmac", table_name="orders")
    for col in ["payment_access_token_expires_at", "payment_access_token_key_version", "payment_access_token_hmac"]:
        if _has_column("orders", col):
            op.drop_column("orders", col)

    if _has_table("payment_capability_sessions"):
        if _has_index("payment_capability_sessions", "ix_payment_capability_sessions_token_hmac"):
            op.drop_index("ix_payment_capability_sessions_token_hmac", table_name="payment_capability_sessions")
        if _has_index("payment_capability_sessions", "ix_payment_capability_sessions_order_id"):
            op.drop_index("ix_payment_capability_sessions_order_id", table_name="payment_capability_sessions")
        if _has_index("payment_capability_sessions", "ix_payment_capability_sessions_seller_id"):
            op.drop_index("ix_payment_capability_sessions_seller_id", table_name="payment_capability_sessions")
        op.drop_table("payment_capability_sessions")

    if _has_table("payment_capabilities"):
        if _has_index("payment_capabilities", "ix_payment_capabilities_token_hmac"):
            op.drop_index("ix_payment_capabilities_token_hmac", table_name="payment_capabilities")
        if _has_index("payment_capabilities", "ix_payment_capabilities_payment_attempt_id"):
            op.drop_index("ix_payment_capabilities_payment_attempt_id", table_name="payment_capabilities")
        if _has_index("payment_capabilities", "ix_payment_capabilities_order_id"):
            op.drop_index("ix_payment_capabilities_order_id", table_name="payment_capabilities")
        if _has_index("payment_capabilities", "ix_payment_capabilities_seller_id"):
            op.drop_index("ix_payment_capabilities_seller_id", table_name="payment_capabilities")
        op.drop_table("payment_capabilities")

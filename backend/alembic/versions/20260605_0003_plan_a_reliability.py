"""Plan A: reliability, inbox productization, billing metering, performance indexes

Revision ID: 20260605_0003
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa


revision = "20260605_0003"
down_revision = "20260605_0002"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name):
    result = conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"),
        {"t": table_name},
    )
    return result.scalar()


def _column_exists(conn, table_name, column_name):
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c)"
        ),
        {"t": table_name, "c": column_name},
    )
    return result.scalar()


def _index_exists(conn, index_name):
    result = conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = :i)"),
        {"i": index_name},
    )
    return result.scalar()


def upgrade():
    conn = op.get_bind()

    # ══════════════════════════════════════════════════
    # 1. BackgroundJob reliability columns
    # ══════════════════════════════════════════════════
    reliability_cols = {
        "retryable": "BOOLEAN DEFAULT TRUE NOT NULL",
        "last_error_code": "VARCHAR(50) DEFAULT ''",
        "next_run_at": "TIMESTAMP WITH TIME ZONE",
        "locked_at": "TIMESTAMP WITH TIME ZONE",
        "locked_by": "VARCHAR(100) DEFAULT ''",
    }
    for col_name, col_type in reliability_cols.items():
        if not _column_exists(conn, "background_jobs", col_name):
            op.execute(f"ALTER TABLE background_jobs ADD COLUMN {col_name} {col_type}")

    # ══════════════════════════════════════════════════
    # 2. AITrace prompt_version column
    # ══════════════════════════════════════════════════
    if not _column_exists(conn, "ai_traces", "prompt_version"):
        op.execute("ALTER TABLE ai_traces ADD COLUMN prompt_version VARCHAR(50) DEFAULT ''")

    # ══════════════════════════════════════════════════
    # 3. Prompt registry table
    # ══════════════════════════════════════════════════
    if not _table_exists(conn, "prompt_versions"):
        op.create_table(
            "prompt_versions",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("prompt_key", sa.String(100), nullable=False, index=True),
            sa.Column("version", sa.Integer, nullable=False, default=1),
            sa.Column("content", sa.Text, nullable=False, default=""),
            sa.Column("description", sa.String(500), default=""),
            sa.Column("is_active", sa.Boolean, default=True, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ══════════════════════════════════════════════════
    # 4. Inbox productization tables
    # ══════════════════════════════════════════════════
    if not _table_exists(conn, "inbox_thread_labels"):
        op.create_table(
            "inbox_thread_labels",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("thread_id", sa.Integer, sa.ForeignKey("inbox_threads.id"), nullable=False, index=True),
            sa.Column("label", sa.String(100), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("thread_id", "label", name="uq_thread_label"),
        )

    if not _table_exists(conn, "inbox_internal_notes"):
        op.create_table(
            "inbox_internal_notes",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("thread_id", sa.Integer, sa.ForeignKey("inbox_threads.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("content", sa.Text, nullable=False, default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _table_exists(conn, "canned_replies"):
        op.create_table(
            "canned_replies",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("content", sa.Text, nullable=False, default=""),
            sa.Column("category", sa.String(100), default="general"),
            sa.Column("usage_count", sa.Integer, default=0),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
        )

    # ══════════════════════════════════════════════════
    # 5. Usage event ledger
    # ══════════════════════════════════════════════════
    if not _table_exists(conn, "usage_events"):
        op.create_table(
            "usage_events",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("metric", sa.String(100), nullable=False, index=True),
            sa.Column("quantity", sa.Integer, default=1, nullable=False),
            sa.Column("source", sa.String(100), default="", nullable=False),
            sa.Column("source_id", sa.String(255), default=""),
            sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True, index=True),
            sa.Column("period", sa.String(20), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ══════════════════════════════════════════════════
    # 6. Performance indexes
    # ══════════════════════════════════════════════════
    indexes = [
        ("ix_inbox_threads_seller_lastmsg", "inbox_threads", ["seller_id", "last_message_at"]),
        ("ix_inbox_messages_thread_created", "inbox_messages", ["thread_id", "created_at"]),
        ("ix_orders_seller_status_created", "orders", ["seller_id", "status", "created_at"]),
        ("ix_usage_counters_seller_metric_period", "usage_counters", ["seller_id", "metric", "period"]),
        ("ix_jobs_status_next_run", "background_jobs", ["status", "next_run_at"]),
        ("ix_ai_traces_seller_status", "ai_traces", ["seller_id", "status"]),
    ]
    for idx_name, table_name, columns in indexes:
        if _table_exists(conn, table_name) and not _index_exists(conn, idx_name):
            col_list = ", ".join(columns)
            op.execute(f"CREATE INDEX {idx_name} ON {table_name} ({col_list})")


def downgrade():
    # Drop indexes
    indexes = [
        "ix_inbox_threads_seller_lastmsg",
        "ix_inbox_messages_thread_created",
        "ix_orders_seller_status_created",
        "ix_usage_counters_seller_metric_period",
        "ix_jobs_status_next_run",
        "ix_ai_traces_seller_status",
    ]
    for idx in indexes:
        op.execute(f"DROP INDEX IF EXISTS {idx}")

    # Drop tables
    op.drop_table("usage_events")
    op.drop_table("canned_replies")
    op.drop_table("inbox_internal_notes")
    op.drop_table("inbox_thread_labels")
    op.drop_table("prompt_versions")

    # Drop columns
    for col in ["retryable", "last_error_code", "next_run_at", "locked_at", "locked_by"]:
        op.execute(f"ALTER TABLE background_jobs DROP COLUMN IF EXISTS {col}")
    op.execute("ALTER TABLE ai_traces DROP COLUMN IF EXISTS prompt_version")

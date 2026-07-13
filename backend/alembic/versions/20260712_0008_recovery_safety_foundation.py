"""Recovery safety foundation — queue safety schema (P1.1)"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260712_0008"
down_revision = "20260706_0007"
branch_labels = None
depends_on = None


def upgrade():
    # ── AgentPolicy: safe defaults and new recovery fields ──
    # Change allow_auto_followup server_default to false for new rows (existing true preserved)
    op.alter_column(
        "agent_policies",
        "allow_auto_followup",
        existing_type=sa.Boolean(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )

    # Add version
    op.add_column(
        "agent_policies",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    # payment_recovery_mode
    op.add_column(
        "agent_policies",
        sa.Column("payment_recovery_mode", sa.String(length=30), nullable=False, server_default="observe"),
    )
    # payment_recovery_paused
    op.add_column(
        "agent_policies",
        sa.Column("payment_recovery_paused", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    # timezone
    op.add_column(
        "agent_policies",
        sa.Column("timezone", sa.String(length=50), nullable=False, server_default="Asia/Jakarta"),
    )
    # quiet_hours
    op.add_column(
        "agent_policies",
        sa.Column("quiet_hours_start", sa.Time(), nullable=True),
    )
    op.add_column(
        "agent_policies",
        sa.Column("quiet_hours_end", sa.Time(), nullable=True),
    )
    # caps
    op.add_column(
        "agent_policies",
        sa.Column("daily_recipient_cap", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "agent_policies",
        sa.Column("order_cycle_cap", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "agent_policies",
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False, server_default="1440"),
    )

    # ── BackgroundJob: lease/fencing and safety fields ──
    op.add_column(
        "background_jobs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "background_jobs",
        sa.Column("claim_token", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "background_jobs",
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "background_jobs",
        sa.Column("execution_stage", sa.String(length=30), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "background_jobs",
        sa.Column("side_effect_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "background_jobs",
        sa.Column("payload_digest", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "background_jobs",
        sa.Column("handler_contract_version", sa.Integer(), nullable=True),
    )

    # Change retryable server_default to false (new jobs default false)
    op.alter_column(
        "background_jobs",
        "retryable",
        existing_type=sa.Boolean(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )

    # Backfill: set legacy queued/failed/running jobs to non-retryable and unknown stage
    # Except we keep unknown stage as default, but ensure retryable false for safety
    # Allowlist for safe retryable will be handled at application layer, migration sets all legacy to false first
    op.execute(
        """
        UPDATE background_jobs
        SET retryable = false,
            execution_stage = COALESCE(execution_stage, 'unknown')
        WHERE status IN ('queued', 'failed', 'running')
        """
    )

    # For rows that were already done/dead_letter etc, ensure execution_stage at least unknown
    op.execute(
        """
        UPDATE background_jobs
        SET execution_stage = 'unknown'
        WHERE execution_stage IS NULL
        """
    )

    # Index for processable jobs (status + execution_stage + next_run_at + lease)
    op.create_index(
        "ix_jobs_processable",
        "background_jobs",
        ["status", "execution_stage", "next_run_at", "lease_expires_at"],
        unique=False,
    )

    # Partial index for queued processable (optional, but helpful)
    # Using WHERE clause if PG supports it
    try:
        op.create_index(
            "ix_jobs_queued_processable",
            "background_jobs",
            ["next_run_at", "id"],
            unique=False,
            postgresql_where=sa.text("status = 'queued' AND execution_stage = 'pre_side_effect'"),
        )
    except Exception:
        # Fallback without where if not supported in this context
        pass

    # ── WebhookEvent: tenant mapping ──
    op.add_column(
        "webhook_events",
        sa.Column("seller_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "webhook_events",
        sa.Column("provider_account_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "webhook_events",
        sa.Column("channel_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_webhook_events_seller_id", "webhook_events", ["seller_id"], unique=False)
    op.create_index("ix_webhook_events_provider_account_id", "webhook_events", ["provider_account_id"], unique=False)
    op.create_index("ix_webhook_events_channel_id", "webhook_events", ["channel_id"], unique=False)

    # ── PaymentAttempt: immutable payment-cycle source ──
    op.create_table(
        "payment_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_account_id", sa.String(length=100), nullable=True),
        sa.Column("external_attempt_id", sa.String(length=255), nullable=True),
        sa.Column("attempt_version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="IDR"),
        sa.Column("payment_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trusted_link_reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("seller_id", "order_id", "attempt_version", name="uq_payment_attempt_seller_order_version"),
        sa.UniqueConstraint(
            "provider", "provider_account_id", "external_attempt_id",
            name="uq_payment_attempt_provider_account_external",
        ),
    )
    op.create_index("ix_payment_attempts_seller_id", "payment_attempts", ["seller_id"], unique=False)
    op.create_index("ix_payment_attempts_order_id", "payment_attempts", ["order_id"], unique=False)
    op.create_index("ix_payment_attempts_provider_account_id", "payment_attempts", ["provider_account_id"], unique=False)
    op.create_index("ix_payment_attempts_external_attempt_id", "payment_attempts", ["external_attempt_id"], unique=False)
    op.create_index("ix_payment_attempt_current", "payment_attempts", ["seller_id", "order_id", "is_current"], unique=False)
    # Partial unique for exactly one current attempt per seller/order
    op.execute(
        """
        CREATE UNIQUE INDEX uq_payment_attempt_one_current_per_order
        ON payment_attempts (seller_id, order_id)
        WHERE is_current = true
        """
    )


def downgrade():
    # Drop payment_attempts
    op.execute("DROP INDEX IF EXISTS uq_payment_attempt_one_current_per_order")
    op.drop_index("ix_payment_attempt_current", table_name="payment_attempts")
    op.drop_index("ix_payment_attempts_external_attempt_id", table_name="payment_attempts")
    op.drop_index("ix_payment_attempts_provider_account_id", table_name="payment_attempts")
    op.drop_index("ix_payment_attempts_order_id", table_name="payment_attempts")
    op.drop_index("ix_payment_attempts_seller_id", table_name="payment_attempts")
    op.drop_table("payment_attempts")

    # WebhookEvent columns
    op.drop_index("ix_webhook_events_channel_id", table_name="webhook_events")
    op.drop_index("ix_webhook_events_provider_account_id", table_name="webhook_events")
    op.drop_index("ix_webhook_events_seller_id", table_name="webhook_events")
    op.drop_column("webhook_events", "channel_id")
    op.drop_column("webhook_events", "provider_account_id")
    op.drop_column("webhook_events", "seller_id")

    # BackgroundJob columns
    op.drop_index("ix_jobs_queued_processable", table_name="background_jobs")
    op.drop_index("ix_jobs_processable", table_name="background_jobs")
    op.drop_column("background_jobs", "handler_contract_version")
    op.drop_column("background_jobs", "payload_digest")
    op.drop_column("background_jobs", "side_effect_started_at")
    op.drop_column("background_jobs", "execution_stage")
    op.drop_column("background_jobs", "lock_version")
    op.drop_column("background_jobs", "claim_token")
    op.drop_column("background_jobs", "lease_expires_at")
    op.alter_column(
        "background_jobs",
        "retryable",
        existing_type=sa.Boolean(),
        server_default=sa.text("true"),
        existing_nullable=False,
    )

    # AgentPolicy columns
    op.drop_column("agent_policies", "cooldown_minutes")
    op.drop_column("agent_policies", "order_cycle_cap")
    op.drop_column("agent_policies", "daily_recipient_cap")
    op.drop_column("agent_policies", "quiet_hours_end")
    op.drop_column("agent_policies", "quiet_hours_start")
    op.drop_column("agent_policies", "timezone")
    op.drop_column("agent_policies", "payment_recovery_paused")
    op.drop_column("agent_policies", "payment_recovery_mode")
    op.drop_column("agent_policies", "version")
    op.alter_column(
        "agent_policies",
        "allow_auto_followup",
        existing_type=sa.Boolean(),
        server_default=sa.text("true"),
        existing_nullable=False,
    )

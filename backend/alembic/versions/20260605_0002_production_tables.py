"""production tables and columns

Revision ID: 20260605_0002
Revises: 20260604_0001
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa

revision = "20260605_0002"
down_revision = "20260604_0001"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    """Check if table exists using inspection (works on PostgreSQL)."""
    from alembic import context
    conn = context.get_bind()
    return sa.inspect(conn).has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    from alembic import context
    conn = context.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(table_name):
        return False
    columns = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    # ── webhook_events ──
    if not _table_exists("webhook_events"):
        op.create_table(
            "webhook_events",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("provider", sa.String(50), nullable=False, index=True),
            sa.Column("event_type", sa.String(100), server_default="", index=True),
            sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True, index=True),
            sa.Column("external_event_id", sa.String(255), server_default="", index=True),
            sa.Column("status", sa.String(20), server_default="received", nullable=False),
            sa.Column("payload", sa.JSON, server_default="{}"),
            sa.Column("error_message", sa.Text, server_default=""),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── background_jobs ──
    if not _table_exists("background_jobs"):
        op.create_table(
            "background_jobs",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("job_type", sa.String(100), nullable=False, index=True),
            sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True, index=True),
            sa.Column("status", sa.String(20), server_default="queued", nullable=False),
            sa.Column("payload", sa.JSON, server_default="{}"),
            sa.Column("attempts", sa.Integer, server_default="0"),
            sa.Column("max_attempts", sa.Integer, server_default="3"),
            sa.Column("error_message", sa.Text, server_default=""),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    # ── audit_logs ──
    if not _table_exists("audit_logs"):
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("actor_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("actor_type", sa.String(50), server_default="system", nullable=False),
            sa.Column("action", sa.String(100), nullable=False, index=True),
            sa.Column("entity_type", sa.String(100), nullable=False, index=True),
            sa.Column("entity_id", sa.String(100), server_default="", index=True),
            sa.Column("before", sa.JSON, server_default="{}"),
            sa.Column("after", sa.JSON, server_default="{}"),
            sa.Column("metadata_json", sa.JSON, server_default="{}"),
            sa.Column("request_id", sa.String(100), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── integration_accounts ──
    if not _table_exists("integration_accounts"):
        op.create_table(
            "integration_accounts",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("provider_type", sa.String(50), nullable=False, index=True),
            sa.Column("provider", sa.String(50), nullable=False, index=True),
            sa.Column("status", sa.String(20), server_default="inactive", nullable=False),
            sa.Column("display_name", sa.String(255), server_default=""),
            sa.Column("config_encrypted", sa.Text, server_default=""),
            sa.Column("capabilities", sa.JSON, server_default="[]"),
            sa.Column("last_health_status", sa.String(20), server_default="unknown"),
            sa.Column("last_health_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("seller_id", "provider_type", "provider", name="uq_integration_account_provider"),
        )

    # ── channels ──
    if not _table_exists("channels"):
        op.create_table(
            "channels",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("type", sa.String(50), nullable=False, index=True),
            sa.Column("provider", sa.String(50), nullable=False, index=True),
            sa.Column("external_id", sa.String(255), server_default="", index=True),
            sa.Column("display_name", sa.String(255), server_default=""),
            sa.Column("status", sa.String(20), server_default="inactive", nullable=False),
            sa.Column("config_encrypted", sa.Text, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("seller_id", "type", "provider", "external_id", name="uq_channel_external"),
        )

    # ── channel_contacts ──
    if not _table_exists("channel_contacts"):
        op.create_table(
            "channel_contacts",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("channel_id", sa.Integer, sa.ForeignKey("channels.id"), nullable=False, index=True),
            sa.Column("external_id", sa.String(255), nullable=False, index=True),
            sa.Column("phone", sa.String(50), server_default="", index=True),
            sa.Column("name", sa.String(255), server_default="Customer"),
            sa.Column("profile", sa.JSON, server_default="{}"),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("seller_id", "channel_id", "external_id", name="uq_channel_contact_external"),
        )

    # ── inbox_threads ──
    if not _table_exists("inbox_threads"):
        op.create_table(
            "inbox_threads",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("channel_id", sa.Integer, sa.ForeignKey("channels.id"), nullable=False, index=True),
            sa.Column("contact_id", sa.Integer, sa.ForeignKey("channel_contacts.id"), nullable=False, index=True),
            sa.Column("conversation_id", sa.Integer, sa.ForeignKey("conversations.id"), nullable=True, index=True),
            sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=True, index=True),
            sa.Column("external_thread_id", sa.String(255), server_default="", index=True),
            sa.Column("mode", sa.String(20), server_default="ai", nullable=False),
            sa.Column("status", sa.String(20), server_default="open", nullable=False),
            sa.Column("stage", sa.String(50), server_default="new"),
            sa.Column("last_message_preview", sa.String(500), server_default=""),
            sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("unread_count", sa.Integer, server_default="0"),
            sa.Column("tags", sa.JSON, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("seller_id", "channel_id", "contact_id", name="uq_inbox_thread_contact"),
        )
    else:
        # Add customer_id column to existing inbox_threads if missing
        if not _column_exists("inbox_threads", "customer_id"):
            op.add_column("inbox_threads", sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=True, index=True))

    # ── inbox_messages ──
    if not _table_exists("inbox_messages"):
        op.create_table(
            "inbox_messages",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("thread_id", sa.Integer, sa.ForeignKey("inbox_threads.id"), nullable=False, index=True),
            sa.Column("direction", sa.String(20), nullable=False),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("content_type", sa.String(50), server_default="text"),
            sa.Column("content", sa.Text, server_default=""),
            sa.Column("external_message_id", sa.String(255), server_default="", index=True),
            sa.Column("status", sa.String(20), server_default="received"),
            sa.Column("raw_payload", sa.JSON, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── customers ──
    if not _table_exists("customers"):
        op.create_table(
            "customers",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("memory_id", sa.Integer, sa.ForeignKey("customer_memories.id"), nullable=True, index=True),
            sa.Column("name", sa.String(255), server_default="Customer"),
            sa.Column("phone", sa.String(50), server_default="", index=True),
            sa.Column("email", sa.String(255), server_default="", index=True),
            sa.Column("whatsapp_id", sa.String(255), server_default="", index=True),
            sa.Column("session_id", sa.String(255), server_default="", index=True),
            sa.Column("tags", sa.JSON, server_default="[]"),
            sa.Column("total_orders", sa.Integer, server_default="0"),
            sa.Column("total_spent", sa.Float, server_default="0"),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("seller_id", "phone", name="uq_customer_phone_per_seller"),
        )

    # ── customer_profiles ──
    if not _table_exists("customer_profiles"):
        op.create_table(
            "customer_profiles",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=False, unique=True, index=True),
            sa.Column("preferences", sa.JSON, server_default="[]"),
            sa.Column("budget_range", sa.String(100), server_default=""),
            sa.Column("sizes", sa.JSON, server_default="[]"),
            sa.Column("address_book", sa.JSON, server_default="[]"),
            sa.Column("notes", sa.Text, server_default=""),
            sa.Column("sentiment", sa.String(20), server_default="neutral"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── customer_events ──
    if not _table_exists("customer_events"):
        op.create_table(
            "customer_events",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=False, index=True),
            sa.Column("event_type", sa.String(100), nullable=False, index=True),
            sa.Column("title", sa.String(255), server_default=""),
            sa.Column("data", sa.JSON, server_default="{}"),
            sa.Column("source", sa.String(50), server_default="system"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── customer_tags ──
    if not _table_exists("customer_tags"):
        op.create_table(
            "customer_tags",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("color", sa.String(20), server_default="#22C55E"),
            sa.Column("description", sa.String(255), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("seller_id", "name", name="uq_customer_tag_name_per_seller"),
        )

    # ── ai_traces ──
    if not _table_exists("ai_traces"):
        op.create_table(
            "ai_traces",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("conversation_id", sa.Integer, sa.ForeignKey("conversations.id"), nullable=True, index=True),
            sa.Column("trace_id", sa.String(100), nullable=False, unique=True, index=True),
            sa.Column("provider", sa.String(50), server_default=""),
            sa.Column("model", sa.String(100), server_default=""),
            sa.Column("stage", sa.String(50), server_default=""),
            sa.Column("status", sa.String(20), server_default="ok", index=True),
            sa.Column("prompt_preview", sa.Text, server_default=""),
            sa.Column("response_preview", sa.Text, server_default=""),
            sa.Column("latency_ms", sa.Integer, server_default="0"),
            sa.Column("tokens_in", sa.Integer, server_default="0"),
            sa.Column("tokens_out", sa.Integer, server_default="0"),
            sa.Column("confidence", sa.Float, server_default="0"),
            sa.Column("error_message", sa.Text, server_default=""),
            sa.Column("metadata_json", sa.JSON, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── ai_tool_calls ──
    if not _table_exists("ai_tool_calls"):
        op.create_table(
            "ai_tool_calls",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("trace_id", sa.String(100), nullable=False, index=True),
            sa.Column("tool_name", sa.String(100), nullable=False),
            sa.Column("status", sa.String(20), server_default="ok"),
            sa.Column("input_json", sa.JSON, server_default="{}"),
            sa.Column("output_json", sa.JSON, server_default="{}"),
            sa.Column("error_message", sa.Text, server_default=""),
            sa.Column("latency_ms", sa.Integer, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── ai_retrieval_logs ──
    if not _table_exists("ai_retrieval_logs"):
        op.create_table(
            "ai_retrieval_logs",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("trace_id", sa.String(100), nullable=False, index=True),
            sa.Column("query", sa.Text, server_default=""),
            sa.Column("product_ids", sa.JSON, server_default="[]"),
            sa.Column("scores", sa.JSON, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── ai_feedback ──
    if not _table_exists("ai_feedback"):
        op.create_table(
            "ai_feedback",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("message_id", sa.Integer, nullable=True, index=True),
            sa.Column("trace_id", sa.String(100), server_default="", index=True),
            sa.Column("rating", sa.String(20), nullable=False),
            sa.Column("reason", sa.String(100), server_default=""),
            sa.Column("note", sa.Text, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    else:
        if not _column_exists("ai_feedback", "message_id"):
            op.add_column("ai_feedback", sa.Column("message_id", sa.Integer, nullable=True, index=True))

    # ── ai_eval_cases ──
    if not _table_exists("ai_eval_cases"):
        op.create_table(
            "ai_eval_cases",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("category", sa.String(100), server_default=""),
            sa.Column("prompt", sa.Text, nullable=False),
            sa.Column("expected_behavior", sa.Text, server_default=""),
            sa.Column("metadata_json", sa.JSON, server_default="{}"),
            sa.Column("is_active", sa.Integer, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── ai_eval_runs ──
    if not _table_exists("ai_eval_runs"):
        op.create_table(
            "ai_eval_runs",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("status", sa.String(20), server_default="queued"),
            sa.Column("total_cases", sa.Integer, server_default="0"),
            sa.Column("passed_cases", sa.Integer, server_default="0"),
            sa.Column("failed_cases", sa.Integer, server_default="0"),
            sa.Column("result_json", sa.JSON, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── campaigns ──
    if not _table_exists("campaigns"):
        op.create_table(
            "campaigns",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("segment", sa.String(100), server_default="all"),
            sa.Column("channel", sa.String(50), server_default="whatsapp"),
            sa.Column("content", sa.Text, server_default=""),
            sa.Column("status", sa.String(20), server_default="draft", index=True),
            sa.Column("generated_by", sa.String(50), server_default="ai"),
            sa.Column("metadata_json", sa.JSON, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    # ── campaign_recipients ──
    if not _table_exists("campaign_recipients"):
        op.create_table(
            "campaign_recipients",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id"), nullable=False, index=True),
            sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=True, index=True),
            sa.Column("name", sa.String(255), server_default=""),
            sa.Column("phone", sa.String(50), server_default=""),
            sa.Column("status", sa.String(20), server_default="pending"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── campaign_messages ──
    if not _table_exists("campaign_messages"):
        op.create_table(
            "campaign_messages",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id"), nullable=False, index=True),
            sa.Column("recipient_id", sa.Integer, sa.ForeignKey("campaign_recipients.id"), nullable=True, index=True),
            sa.Column("status", sa.String(20), server_default="queued"),
            sa.Column("content", sa.Text, server_default=""),
            sa.Column("provider_message_id", sa.String(255), server_default=""),
            sa.Column("error_message", sa.Text, server_default=""),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── automation_rules ──
    if not _table_exists("automation_rules"):
        op.create_table(
            "automation_rules",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("template_key", sa.String(100), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("status", sa.String(20), server_default="active", index=True),
            sa.Column("trigger_json", sa.JSON, server_default="{}"),
            sa.Column("action_json", sa.JSON, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    # ── automation_runs ──
    if not _table_exists("automation_runs"):
        op.create_table(
            "automation_runs",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("rule_id", sa.Integer, sa.ForeignKey("automation_rules.id"), nullable=True, index=True),
            sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True, index=True),
            sa.Column("status", sa.String(20), server_default="running"),
            sa.Column("context_json", sa.JSON, server_default="{}"),
            sa.Column("error_message", sa.Text, server_default=""),
            sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        )

    # ── automation_run_steps ──
    if not _table_exists("automation_run_steps"):
        op.create_table(
            "automation_run_steps",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("run_id", sa.Integer, sa.ForeignKey("automation_runs.id"), nullable=False, index=True),
            sa.Column("step_type", sa.String(100), nullable=False),
            sa.Column("status", sa.String(20), server_default="ok"),
            sa.Column("input_json", sa.JSON, server_default="{}"),
            sa.Column("output_json", sa.JSON, server_default="{}"),
            sa.Column("error_message", sa.Text, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── plans ──
    if not _table_exists("plans"):
        op.create_table(
            "plans",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("code", sa.String(50), nullable=False, unique=True, index=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("price_monthly", sa.Float, server_default="0"),
            sa.Column("limits", sa.JSON, server_default="{}"),
            sa.Column("is_active", sa.Integer, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── subscriptions ──
    if not _table_exists("subscriptions"):
        op.create_table(
            "subscriptions",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("plan_code", sa.String(50), nullable=False, index=True),
            sa.Column("status", sa.String(20), server_default="active"),
            sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
            sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column("override_limits", sa.JSON, server_default="{}"),
            sa.Column("metadata_json", sa.JSON, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
    else:
        if not _column_exists("subscriptions", "override_limits"):
            op.add_column("subscriptions", sa.Column("override_limits", sa.JSON, server_default="{}"))

    # ── usage_counters ──
    if not _table_exists("usage_counters"):
        op.create_table(
            "usage_counters",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("metric", sa.String(100), nullable=False, index=True),
            sa.Column("period", sa.String(20), nullable=False, index=True),
            sa.Column("used", sa.Integer, server_default="0"),
            sa.Column("limit_value", sa.Integer, server_default="0"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("seller_id", "metric", "period", name="uq_usage_counter_period"),
        )

    # ── billing_events ──
    if not _table_exists("billing_events"):
        op.create_table(
            "billing_events",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("event_type", sa.String(100), nullable=False, index=True),
            sa.Column("provider", sa.String(50), server_default=""),
            sa.Column("payload", sa.JSON, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── product_import_batches ──
    if not _table_exists("product_import_batches"):
        op.create_table(
            "product_import_batches",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("preview_token", sa.String(100), nullable=False, unique=True, index=True),
            sa.Column("filename", sa.String(255), server_default=""),
            sa.Column("rows_json", sa.JSON, server_default="[]"),
            sa.Column("errors_json", sa.JSON, server_default="[]"),
            sa.Column("status", sa.String(20), server_default="preview"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        )

    # ── system_heartbeats ──
    if not _table_exists("system_heartbeats"):
        op.create_table(
            "system_heartbeats",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("service", sa.String(100), nullable=False, unique=True, index=True),
            sa.Column("status", sa.String(20), server_default="alive"),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("metadata_json", sa.JSON, server_default="{}"),
        )

    # ── Order payment columns (for VPS installs that didn't have them yet) ──
    for col_name, col_type in [
        ("payment_invoice_id", sa.String(100)),
        ("payment_access_token", sa.String(100)),
        ("payment_qr_data", sa.Text),
        ("payment_va_number", sa.String(100)),
        ("payment_expires_at", sa.String(100)),
    ]:
        if not _column_exists("orders", col_name):
            op.add_column("orders", sa.Column(col_name, col_type, nullable=True))

    # ── Indexes on orders ──
    try:
        op.create_index("ix_orders_payment_invoice_id", "orders", ["payment_invoice_id"], unique=False, if_not_exists=True)
    except Exception:
        pass
    try:
        op.create_index("ix_orders_payment_access_token", "orders", ["payment_access_token"], unique=False, if_not_exists=True)
    except Exception:
        pass


def downgrade():
    # Only drop tables created in this migration.
    # Order matters: drop dependents first.
    for table_name in [
        "system_heartbeats",
        "product_import_batches",
        "billing_events",
        "usage_counters",
        "subscriptions",
        "plans",
        "automation_run_steps",
        "automation_runs",
        "automation_rules",
        "campaign_messages",
        "campaign_recipients",
        "campaigns",
        "ai_eval_runs",
        "ai_eval_cases",
        "ai_feedback",
        "ai_retrieval_logs",
        "ai_tool_calls",
        "ai_traces",
        "customer_tags",
        "customer_events",
        "customer_profiles",
        "customers",
        "inbox_messages",
        "inbox_threads",
        "channel_contacts",
        "channels",
        "integration_accounts",
        "audit_logs",
        "background_jobs",
        "webhook_events",
    ]:
        op.drop_table(table_name)

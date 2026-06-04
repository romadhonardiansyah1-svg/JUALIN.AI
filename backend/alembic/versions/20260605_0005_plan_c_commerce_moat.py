"""Plan C: AI Commerce Moat — referral, lead, playbook, scoring, offer, knowledge, qa_review, experiment

Revision ID: 20260605_0005
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa

revision = "20260605_0005"
down_revision = "20260605_0004"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name):
    result = conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"),
        {"t": table_name},
    )
    return result.scalar()


def upgrade():
    conn = op.get_bind()

    # 1. Referral system
    if not _table_exists(conn, "referral_codes"):
        op.create_table(
            "referral_codes",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("code", sa.String(50), nullable=False, unique=True, index=True),
            sa.Column("description", sa.String(255), default=""),
            sa.Column("commission_percent", sa.Float, default=5.0),
            sa.Column("expiry_days", sa.Integer, default=30),
            sa.Column("is_active", sa.Boolean, default=True, nullable=False),
            sa.Column("total_clicks", sa.Integer, default=0),
            sa.Column("total_conversions", sa.Integer, default=0),
            sa.Column("total_revenue", sa.Float, default=0),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _table_exists(conn, "referral_events"):
        op.create_table(
            "referral_events",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("referral_code_id", sa.Integer, sa.ForeignKey("referral_codes.id"), nullable=False, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("event_type", sa.String(30), nullable=False, index=True),
            sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id"), nullable=True),
            sa.Column("order_value", sa.Float, default=0),
            sa.Column("commission_amount", sa.Float, default=0),
            sa.Column("ip_address", sa.String(45), default=""),
            sa.Column("metadata_json", sa.JSON, default=dict),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _table_exists(conn, "reseller_profiles"):
        op.create_table(
            "reseller_profiles",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("email", sa.String(255), default=""),
            sa.Column("phone", sa.String(20), default=""),
            sa.Column("referral_code_id", sa.Integer, sa.ForeignKey("referral_codes.id"), nullable=True),
            sa.Column("total_earned", sa.Float, default=0),
            sa.Column("status", sa.String(20), default="active", index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _table_exists(conn, "commission_rules"):
        op.create_table(
            "commission_rules",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("type", sa.String(30), default="percentage"),
            sa.Column("value", sa.Float, default=5.0),
            sa.Column("min_order_value", sa.Float, default=0),
            sa.Column("product_category", sa.String(100), default=""),
            sa.Column("is_active", sa.Boolean, default=True, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _table_exists(conn, "commission_events"):
        op.create_table(
            "commission_events",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("reseller_id", sa.Integer, sa.ForeignKey("reseller_profiles.id"), nullable=True),
            sa.Column("referral_event_id", sa.Integer, sa.ForeignKey("referral_events.id"), nullable=True),
            sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id"), nullable=True),
            sa.Column("amount", sa.Float, default=0),
            sa.Column("status", sa.String(20), default="pending", index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # 2. Lead capture
    if not _table_exists(conn, "lead_forms"):
        op.create_table(
            "lead_forms",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("slug", sa.String(100), nullable=False, unique=True, index=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, default=""),
            sa.Column("fields_json", sa.JSON, default=list),
            sa.Column("success_message", sa.String(500), default=""),
            sa.Column("is_active", sa.Boolean, default=True, nullable=False),
            sa.Column("submission_count", sa.Integer, default=0),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    if not _table_exists(conn, "lead_submissions"):
        op.create_table(
            "lead_submissions",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("form_id", sa.Integer, sa.ForeignKey("lead_forms.id"), nullable=False, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("data_json", sa.JSON, default=dict),
            sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("source_ip", sa.String(45), default=""),
            sa.Column("status", sa.String(20), default="new", index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # 3. Sales playbooks
    if not _table_exists(conn, "sales_playbooks"):
        op.create_table(
            "sales_playbooks",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("key", sa.String(50), nullable=False, index=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, default=""),
            sa.Column("prompt_instructions", sa.Text, default=""),
            sa.Column("tone", sa.String(50), default="friendly"),
            sa.Column("is_enabled", sa.Boolean, default=True, nullable=False),
            sa.Column("priority", sa.Integer, default=0),
            sa.Column("trigger_conditions_json", sa.JSON, default=dict),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    if not _table_exists(conn, "sales_playbook_rules"):
        op.create_table(
            "sales_playbook_rules",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("playbook_id", sa.Integer, sa.ForeignKey("sales_playbooks.id"), nullable=False, index=True),
            sa.Column("condition_type", sa.String(50), nullable=False),
            sa.Column("operator", sa.String(20), default="eq"),
            sa.Column("value", sa.String(255), default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # 4. Customer scoring
    if not _table_exists(conn, "customer_scores"):
        op.create_table(
            "customer_scores",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=False, unique=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("purchase_likelihood", sa.Float, default=0),
            sa.Column("repeat_likelihood", sa.Float, default=0),
            sa.Column("churn_risk", sa.Float, default=0),
            sa.Column("value_score", sa.Float, default=0),
            sa.Column("support_risk", sa.Float, default=0),
            sa.Column("overall_score", sa.Float, default=0),
            sa.Column("tier", sa.String(20), default="unknown"),
            sa.Column("reason_codes", sa.JSON, default=list),
            sa.Column("input_signals", sa.JSON, default=dict),
            sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    # 5. Offers
    if not _table_exists(conn, "offers"):
        op.create_table(
            "offers",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("type", sa.String(30), nullable=False, index=True),
            sa.Column("value", sa.Float, default=0),
            sa.Column("value_type", sa.String(20), default="fixed"),
            sa.Column("min_order_value", sa.Float, default=0),
            sa.Column("product_ids_json", sa.JSON, default=list),
            sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("max_redemptions", sa.Integer, default=0),
            sa.Column("current_redemptions", sa.Integer, default=0),
            sa.Column("is_active", sa.Boolean, default=True, nullable=False),
            sa.Column("allow_chat_auto", sa.Boolean, default=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    if not _table_exists(conn, "offer_recommendations"):
        op.create_table(
            "offer_recommendations",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("offer_id", sa.Integer, sa.ForeignKey("offers.id"), nullable=True),
            sa.Column("trigger_type", sa.String(50), nullable=False),
            sa.Column("customer_segment", sa.String(100), default="all"),
            sa.Column("estimated_impact", sa.Float, default=0),
            sa.Column("status", sa.String(20), default="pending", index=True),
            sa.Column("metadata_json", sa.JSON, default=dict),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _table_exists(conn, "offer_redemptions"):
        op.create_table(
            "offer_redemptions",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("offer_id", sa.Integer, sa.ForeignKey("offers.id"), nullable=False, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id"), nullable=True),
            sa.Column("discount_applied", sa.Float, default=0),
            sa.Column("channel", sa.String(30), default="chat"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # 6. Knowledge base
    if not _table_exists(conn, "knowledge_sources"):
        op.create_table(
            "knowledge_sources",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("type", sa.String(30), nullable=False, index=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("content", sa.Text, default=""),
            sa.Column("status", sa.String(20), default="active", index=True),
            sa.Column("chunk_count", sa.Integer, default=0),
            sa.Column("metadata_json", sa.JSON, default=dict),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    if not _table_exists(conn, "knowledge_chunks"):
        op.create_table(
            "knowledge_chunks",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("source_id", sa.Integer, sa.ForeignKey("knowledge_sources.id"), nullable=False, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("content", sa.Text, nullable=False),
            sa.Column("chunk_index", sa.Integer, default=0),
            sa.Column("token_count", sa.Integer, default=0),
            sa.Column("metadata_json", sa.JSON, default=dict),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # 7. QA review queue
    if not _table_exists(conn, "qa_review_items"):
        op.create_table(
            "qa_review_items",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("type", sa.String(50), nullable=False, index=True),
            sa.Column("status", sa.String(20), default="pending", index=True),
            sa.Column("priority", sa.String(10), default="medium"),
            sa.Column("thread_id", sa.Integer, sa.ForeignKey("inbox_threads.id"), nullable=True),
            sa.Column("message_id", sa.Integer, sa.ForeignKey("inbox_messages.id"), nullable=True),
            sa.Column("trace_id", sa.Integer, sa.ForeignKey("ai_traces.id"), nullable=True),
            sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id"), nullable=True),
            sa.Column("original_content", sa.Text, default=""),
            sa.Column("edited_content", sa.Text, default=""),
            sa.Column("reason", sa.Text, default=""),
            sa.Column("reviewer_notes", sa.Text, default=""),
            sa.Column("reviewed_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.JSON, default=dict),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    # 8. Experiments
    if not _table_exists(conn, "experiments"):
        op.create_table(
            "experiments",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, default=""),
            sa.Column("type", sa.String(50), nullable=False, index=True),
            sa.Column("status", sa.String(20), default="draft", index=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", sa.JSON, default=dict),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    if not _table_exists(conn, "experiment_variants"):
        op.create_table(
            "experiment_variants",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("experiment_id", sa.Integer, sa.ForeignKey("experiments.id"), nullable=False, index=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("content", sa.Text, default=""),
            sa.Column("weight", sa.Integer, default=50),
            sa.Column("impressions", sa.Integer, default=0),
            sa.Column("conversions", sa.Integer, default=0),
            sa.Column("revenue", sa.Float, default=0),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _table_exists(conn, "experiment_assignments"):
        op.create_table(
            "experiment_assignments",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("experiment_id", sa.Integer, sa.ForeignKey("experiments.id"), nullable=False, index=True),
            sa.Column("variant_id", sa.Integer, sa.ForeignKey("experiment_variants.id"), nullable=False, index=True),
            sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("session_id", sa.String(100), default="", index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _table_exists(conn, "experiment_events"):
        op.create_table(
            "experiment_events",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("experiment_id", sa.Integer, sa.ForeignKey("experiments.id"), nullable=False, index=True),
            sa.Column("variant_id", sa.Integer, sa.ForeignKey("experiment_variants.id"), nullable=False, index=True),
            sa.Column("assignment_id", sa.Integer, sa.ForeignKey("experiment_assignments.id"), nullable=True),
            sa.Column("event_type", sa.String(50), nullable=False, index=True),
            sa.Column("value", sa.Float, default=0),
            sa.Column("metadata_json", sa.JSON, default=dict),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade():
    for table in [
        "experiment_events", "experiment_assignments", "experiment_variants", "experiments",
        "qa_review_items",
        "knowledge_chunks", "knowledge_sources",
        "offer_redemptions", "offer_recommendations", "offers",
        "customer_scores",
        "sales_playbook_rules", "sales_playbooks",
        "lead_submissions", "lead_forms",
        "commission_events", "reseller_profiles", "referral_events", "referral_codes",
        "commission_rules",
    ]:
        op.drop_table(table)

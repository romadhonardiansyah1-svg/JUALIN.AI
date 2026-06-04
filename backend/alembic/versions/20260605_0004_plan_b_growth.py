"""Plan B: growth, analytics, onboarding, templates, storefront, campaign autopilot

Revision ID: 20260605_0004
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa


revision = "20260605_0004"
down_revision = "20260605_0003"
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

    # 1. Daily seller metrics
    if not _table_exists(conn, "daily_seller_metrics"):
        op.create_table(
            "daily_seller_metrics",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("date", sa.String(10), nullable=False, index=True),
            sa.Column("chats_in", sa.Integer, default=0),
            sa.Column("ai_replies", sa.Integer, default=0),
            sa.Column("orders_created", sa.Integer, default=0),
            sa.Column("orders_paid", sa.Integer, default=0),
            sa.Column("orders_cancelled", sa.Integer, default=0),
            sa.Column("revenue_paid", sa.Float, default=0),
            sa.Column("pending_payment_value", sa.Float, default=0),
            sa.Column("campaign_sent", sa.Integer, default=0),
            sa.Column("campaign_conversions", sa.Integer, default=0),
            sa.Column("repeat_buyer_count", sa.Integer, default=0),
            sa.Column("top_products_json", sa.JSON, default=list),
            sa.Column("extra_json", sa.JSON, default=dict),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("seller_id", "date", name="uq_daily_metric_seller_date"),
        )

    # 2. Templates
    if not _table_exists(conn, "templates"):
        op.create_table(
            "templates",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("type", sa.String(50), nullable=False, index=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, default=""),
            sa.Column("category", sa.String(100), default="general", index=True),
            sa.Column("content_json", sa.JSON, default=dict),
            sa.Column("tags", sa.JSON, default=list),
            sa.Column("is_public", sa.Boolean, default=True, nullable=False),
            sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("usage_count", sa.Integer, default=0),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    # 3. Seller onboarding
    if not _table_exists(conn, "seller_onboarding"):
        op.create_table(
            "seller_onboarding",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, unique=True, index=True),
            sa.Column("step_profile", sa.Boolean, default=False, nullable=False),
            sa.Column("step_product", sa.Boolean, default=False, nullable=False),
            sa.Column("step_payment", sa.Boolean, default=False, nullable=False),
            sa.Column("step_whatsapp", sa.Boolean, default=False, nullable=False),
            sa.Column("step_ai_persona", sa.Boolean, default=False, nullable=False),
            sa.Column("step_test_chat", sa.Boolean, default=False, nullable=False),
            sa.Column("step_go_live", sa.Boolean, default=False, nullable=False),
            sa.Column("current_step", sa.String(50), default="profile"),
            sa.Column("completed", sa.Boolean, default=False, nullable=False),
            sa.Column("metadata_json", sa.JSON, default=dict),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    # 4. Storefronts
    if not _table_exists(conn, "storefronts"):
        op.create_table(
            "storefronts",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, unique=True, index=True),
            sa.Column("slug", sa.String(255), nullable=False, unique=True, index=True),
            sa.Column("title", sa.String(255), default=""),
            sa.Column("tagline", sa.String(500), default=""),
            sa.Column("theme_json", sa.JSON, default=dict),
            sa.Column("is_published", sa.Boolean, default=False, nullable=False),
            sa.Column("seo_title", sa.String(255), default=""),
            sa.Column("seo_description", sa.Text, default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    if not _table_exists(conn, "storefront_sections"):
        op.create_table(
            "storefront_sections",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("storefront_id", sa.Integer, sa.ForeignKey("storefronts.id"), nullable=False, index=True),
            sa.Column("type", sa.String(50), nullable=False),
            sa.Column("title", sa.String(255), default=""),
            sa.Column("content_json", sa.JSON, default=dict),
            sa.Column("order_index", sa.Integer, default=0),
            sa.Column("is_visible", sa.Boolean, default=True, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    # 5. Campaign recommendations
    if not _table_exists(conn, "campaign_recommendations"):
        op.create_table(
            "campaign_recommendations",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("trigger_type", sa.String(100), nullable=False, index=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, default=""),
            sa.Column("suggested_content", sa.Text, default=""),
            sa.Column("target_audience_json", sa.JSON, default=dict),
            sa.Column("estimated_reach", sa.Integer, default=0),
            sa.Column("status", sa.String(20), default="pending", index=True),
            sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id"), nullable=True),
            sa.Column("metadata_json", sa.JSON, default=dict),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )


def downgrade():
    op.drop_table("campaign_recommendations")
    op.drop_table("storefront_sections")
    op.drop_table("storefronts")
    op.drop_table("seller_onboarding")
    op.drop_table("templates")
    op.drop_table("daily_seller_metrics")

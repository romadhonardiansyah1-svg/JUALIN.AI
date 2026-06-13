"""JUALIN OS: agent_policies, agent_runs, agent_approvals, negotiation_states + products.cost_price

Revision ID: 20260613_0006
Revises: 20260605_0005
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa

revision = "20260613_0006"
down_revision = "20260605_0005"
branch_labels = None
depends_on = None


def _table_exists(conn, name):
    return conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"),
        {"t": name},
    ).scalar()


def _column_exists(conn, table, column):
    return conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c)"
        ),
        {"t": table, "c": column},
    ).scalar()


def upgrade():
    conn = op.get_bind()

    if not _column_exists(conn, "products", "cost_price"):
        op.add_column("products", sa.Column("cost_price", sa.Float, server_default="0"))

    if not _table_exists(conn, "agent_policies"):
        op.create_table(
            "agent_policies",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("autonomy_level", sa.String(30), nullable=False, server_default="auto_with_approval"),
            sa.Column("allow_auto_negotiation", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("allow_auto_followup", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("allow_low_stock_alert", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("daily_brief_enabled", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("max_discount_percent", sa.Float, nullable=False, server_default="15"),
            sa.Column("margin_floor_percent", sa.Float, nullable=False, server_default="10"),
            sa.Column("require_approval_above_percent", sa.Float, nullable=False, server_default="10"),
            sa.Column("nego_max_rounds", sa.Integer, nullable=False, server_default="3"),
            sa.Column("low_stock_threshold", sa.Integer, nullable=False, server_default="3"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("seller_id", name="uq_agent_policy_seller"),
        )

    if not _table_exists(conn, "agent_runs"):
        op.create_table(
            "agent_runs",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("agent_role", sa.String(30), nullable=False, index=True),
            sa.Column("trigger", sa.String(30), nullable=False, server_default="chat"),
            sa.Column("status", sa.String(20), nullable=False, server_default="done"),
            sa.Column("summary", sa.String(500), server_default=""),
            sa.Column("detail_json", sa.JSON, server_default="{}"),
            sa.Column("conversation_id", sa.Integer, index=True),
            sa.Column("customer_id", sa.Integer, index=True),
            sa.Column("order_id", sa.Integer, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        )

    if not _table_exists(conn, "agent_approvals"):
        op.create_table(
            "agent_approvals",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("agent_role", sa.String(30), nullable=False, server_default="negotiator"),
            sa.Column("action_type", sa.String(50), nullable=False, index=True),
            sa.Column("title", sa.String(255), server_default=""),
            sa.Column("detail_json", sa.JSON, server_default="{}"),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending", index=True),
            sa.Column("reason", sa.String(500), server_default=""),
            sa.Column("decided_by", sa.Integer),
            sa.Column("decided_at", sa.DateTime(timezone=True)),
            sa.Column("conversation_id", sa.Integer, index=True),
            sa.Column("order_id", sa.Integer, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        )

    if not _table_exists(conn, "negotiation_states"):
        op.create_table(
            "negotiation_states",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("conversation_id", sa.Integer, nullable=False, index=True),
            sa.Column("product_id", sa.Integer, index=True),
            sa.Column("list_price", sa.Float, server_default="0"),
            sa.Column("floor_price", sa.Float, server_default="0"),
            sa.Column("current_offer", sa.Float, server_default="0"),
            sa.Column("last_customer_ask", sa.Float, server_default="0"),
            sa.Column("rounds", sa.Integer, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("history_json", sa.JSON, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )


def downgrade():
    for t in ("negotiation_states", "agent_approvals", "agent_runs", "agent_policies"):
        op.execute(f"DROP TABLE IF EXISTS {t}")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS cost_price")

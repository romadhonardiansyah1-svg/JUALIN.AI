"""Multi-provider LLM registry (llm_providers)"""
from alembic import op
import sqlalchemy as sa

revision = "20260721_0013"
down_revision = "20260717_0012"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if not sa.inspect(conn).has_table("llm_providers"):
        op.create_table(
            "llm_providers",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("label", sa.String(60), server_default=""),
            sa.Column("base_url", sa.String(255), server_default=""),
            sa.Column("model", sa.String(100), server_default=""),
            sa.Column("light_model", sa.String(100), server_default=""),
            sa.Column("fallback_model", sa.String(100), server_default=""),
            sa.Column("api_keys_json", sa.JSON, nullable=True),
            sa.Column("priority", sa.Integer, nullable=False, server_default="100"),
            sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    op.execute("DROP TABLE IF EXISTS llm_providers")

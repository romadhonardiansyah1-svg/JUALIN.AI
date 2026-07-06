"""LLM settings singleton untuk admin control panel"""
from alembic import op
import sqlalchemy as sa

revision = "20260706_0007"
down_revision = "20260613_0006"   # ⚠️ VERIFIKASI: buka 20260613_0006_agent_os.py, salin nilai variabel `revision`-nya ke sini
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if not sa.inspect(conn).has_table("llm_settings"):
        op.create_table(
            "llm_settings",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("provider_label", sa.String(50), server_default="9router"),
            sa.Column("base_url", sa.String(255), server_default=""),
            sa.Column("model", sa.String(100), server_default=""),
            sa.Column("light_model", sa.String(100), server_default=""),
            sa.Column("fallback_model", sa.String(100), server_default=""),
            sa.Column("api_keys_json", sa.JSON, nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    op.execute("DROP TABLE IF EXISTS llm_settings")

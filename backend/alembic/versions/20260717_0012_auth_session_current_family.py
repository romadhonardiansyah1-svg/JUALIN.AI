"""Serialize refresh rotation with one current session per family."""
from alembic import op
import sqlalchemy as sa

revision = "20260717_0012"
down_revision = "20260712_0011"
branch_labels = None
depends_on = None

_INDEX = "uq_auth_sessions_current_family"


def _has_index(name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == name for index in inspector.get_indexes("auth_sessions"))


def upgrade():
    op.execute(sa.text("""
        WITH ranked AS (
            SELECT id, row_number() OVER (
                PARTITION BY family_id
                ORDER BY rotation_counter DESC, created_at DESC, id DESC
            ) AS position
            FROM auth_sessions
            WHERE is_current = true AND revoked_at IS NULL
        )
        UPDATE auth_sessions
        SET is_current = false,
            revoked_at = COALESCE(revoked_at, now()),
            revoked_reason = COALESCE(revoked_reason, 'duplicate_current_cleanup')
        WHERE id IN (SELECT id FROM ranked WHERE position > 1)
    """))
    if not _has_index(_INDEX):
        op.create_index(
            _INDEX,
            "auth_sessions",
            ["family_id"],
            unique=True,
            postgresql_where=sa.text("is_current = true AND revoked_at IS NULL"),
        )


def downgrade():
    if _has_index(_INDEX):
        op.drop_index(_INDEX, table_name="auth_sessions")

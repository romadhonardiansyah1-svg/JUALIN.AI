"""scale up foundation tables

Revision ID: 20260604_0001
Revises:
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa

revision = "20260604_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Baseline current SQLAlchemy metadata so a fresh local/CI database can use
    # `alembic upgrade head` without relying on runtime create_all().
    import models  # noqa: F401
    from models.database import Base

    bind = op.get_bind()
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=bind)


def downgrade():
    pass

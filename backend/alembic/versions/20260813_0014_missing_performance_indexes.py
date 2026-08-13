"""Missing performance indexes (hot-path filters + pgvector ANN on products.embedding)"""
from alembic import op
import sqlalchemy as sa

revision = "20260813_0014"
down_revision = "20260721_0013"
branch_labels = None
depends_on = None


# Plain B-tree indexes: (index_name, table, [columns])
# Skipped on purpose because equivalent indexes already exist:
#   - orders(seller_id, status, created_at): Index("ix_orders_seller_status_created", ...) — models/order.py:139
#   - campaigns.status: already index=True — models/campaign.py:19
#   - campaign_recipients.campaign_id / customer_id: already index=True — models/campaign.py:30-31
#   - chat_analytics.seller_id alone: already index=True (models/chat_analytics.py:24); the
#     composite below is still added because the leading-column index cannot serve the
#     (seller_id, created_at) range/sort combination as well.
BTREE_INDEXES = [
    ("ix_products_seller_active", "products", ["seller_id", "is_active"]),
    ("ix_chat_analytics_seller_created", "chat_analytics", ["seller_id", "created_at"]),
    ("ix_orders_customer_phone", "orders", ["customer_phone"]),
    ("ix_conversations_customer_phone", "conversations", ["customer_phone"]),
    ("ix_customers_last_seen_at", "customers", ["last_seen_at"]),
    ("ix_campaigns_created_at", "campaigns", ["created_at"]),
    ("ix_campaign_recipients_status", "campaign_recipients", ["status"]),
]

VECTOR_INDEX = "ix_products_embedding_cosine"


def _has_table(table: str) -> bool:
    conn = op.get_bind()
    try:
        return sa.inspect(conn).has_table(table)
    except Exception:
        return False


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    try:
        cols = [c["name"] for c in sa.inspect(conn).get_columns(table)]
        return column in cols
    except Exception:
        return False


def _has_index(table: str, index_name: str) -> bool:
    conn = op.get_bind()
    try:
        indexes = [idx["name"] for idx in sa.inspect(conn).get_indexes(table)]
        return index_name in indexes
    except Exception:
        return False


def upgrade():
    for idx_name, table, columns in BTREE_INDEXES:
        if not _has_table(table):
            continue
        if any(not _has_column(table, col) for col in columns):
            continue
        if not _has_index(table, idx_name):
            op.create_index(idx_name, table, columns)

    # ── pgvector ANN index on products.embedding (Vector(384), models/product.py:32) ──
    # Opclass MUST match the distance operator the code actually emits. All three call
    # sites use cosine_distance(), which compiles to `<=>`:
    #   backend/api/routes_products.py:330  .order_by(Product.embedding.cosine_distance(query_embedding))
    #   backend/ai/agent.py:209             .order_by(Product.embedding.cosine_distance(query_embedding))
    #   backend/ai/tools.py:41              .order_by(Product.embedding.cosine_distance(query_embedding))
    # => vector_cosine_ops. vector_l2_ops (`<->`) / vector_ip_ops (`<#>`) would be ignored
    # by the planner for these queries.
    #
    # ivfflat, not hnsw: HNSW was added in pgvector 0.5.0 ("Added HNSW index type",
    # pgvector CHANGELOG 0.5.0 / 2023-08-28), so the 0.3.6 line pinned in
    # requirements.txt has no hnsw access method at all.
    #
    # ponytail: lists=100 is pgvector's default and generous for a small products table
    # (guidance: rows/1000 up to 1M rows). IVFFlat centroids are computed from the rows
    # present at build time — building on an empty/near-empty table yields poor recall,
    # so REINDEX this index once the catalog is populated.
    if _has_table("products") and _has_column("products", "embedding") and not _has_index("products", VECTOR_INDEX):
        op.execute(
            f"CREATE INDEX {VECTOR_INDEX} ON products "
            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        )


def downgrade():
    op.execute(f"DROP INDEX IF EXISTS {VECTOR_INDEX}")
    for idx_name, _table, _columns in reversed(BTREE_INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {idx_name}")

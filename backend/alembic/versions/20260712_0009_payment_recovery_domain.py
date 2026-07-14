"""Payment recovery domain schema — consent, opportunity, dispatch, outcome (P2.1)"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260712_0009"
down_revision = "20260712_0008"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    conn = op.get_bind()
    try:
        inspector = sa.inspect(conn)
        return inspector.has_table(table)
    except Exception:
        return False


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    try:
        inspector = sa.inspect(conn)
        cols = [c["name"] for c in inspector.get_columns(table)]
        return column in cols
    except Exception:
        return False


def _has_index(table: str, index_name: str) -> bool:
    conn = op.get_bind()
    try:
        inspector = sa.inspect(conn)
        indexes = [idx["name"] for idx in inspector.get_indexes(table)]
        return index_name in indexes
    except Exception:
        return False


def upgrade():
    # ── PaymentRecoveryControl singleton ──
    if not _has_table("payment_recovery_controls"):
        op.create_table(
            "payment_recovery_controls",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("reason", sa.String(length=500), server_default=""),
        )

    # ── ContactSubject ──
    if not _has_table("contact_subjects"):
        op.create_table(
            "contact_subjects",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("channel", sa.String(length=20), nullable=False, server_default="whatsapp"),
            sa.Column("address_ciphertext", sa.LargeBinary(), nullable=True),
            sa.Column("address_key_version", sa.Integer(), nullable=True),
            sa.Column("address_revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        )
        op.create_index("ix_contact_subjects_seller_id", "contact_subjects", ["seller_id"])
        op.create_index("ix_contact_subjects_customer_id", "contact_subjects", ["customer_id"])
        op.create_index("ix_contact_subject_seller_channel", "contact_subjects", ["seller_id", "channel"])

    # ── ContactSubjectFingerprint ──
    if not _has_table("contact_subject_fingerprints"):
        op.create_table(
            "contact_subject_fingerprints",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("contact_subject_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contact_subjects.id"), nullable=False),
            sa.Column("channel", sa.String(length=20), nullable=False, server_default="whatsapp"),
            sa.Column("key_version", sa.Integer(), nullable=False),
            sa.Column("fingerprint", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_contact_subject_fingerprints_seller_id", "contact_subject_fingerprints", ["seller_id"])
        op.create_index("ix_contact_subject_fingerprints_contact_subject_id", "contact_subject_fingerprints", ["contact_subject_id"])
        op.create_unique_constraint(
            "uq_contact_fingerprint", "contact_subject_fingerprints",
            ["seller_id", "channel", "key_version", "fingerprint"],
        )

    # ── ContactPermission ──
    if not _has_table("contact_permissions"):
        op.create_table(
            "contact_permissions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("contact_subject_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contact_subjects.id"), nullable=False),
            sa.Column("channel", sa.String(length=20), nullable=False, server_default="whatsapp"),
            sa.Column("address_ciphertext", sa.LargeBinary(), nullable=True),
            sa.Column("address_key_version", sa.Integer(), nullable=True),
            sa.Column("address_fingerprint", sa.String(length=255), nullable=False),
            sa.Column("fingerprint_key_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("purpose", sa.String(length=50), nullable=False, server_default="transactional_payment_reminder"),
            sa.Column("scope_type", sa.String(length=30), nullable=False, server_default="order_payment_cycle"),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
            sa.Column("payment_attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payment_attempts.id"), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("provenance", sa.String(length=50), nullable=False),
            sa.Column("source_reference", sa.String(length=255), nullable=True),
            sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        )
        op.create_index("ix_contact_permissions_seller_id", "contact_permissions", ["seller_id"])
        op.create_index("ix_contact_permissions_contact_subject_id", "contact_permissions", ["contact_subject_id"])
        op.create_index("ix_contact_permissions_order_id", "contact_permissions", ["order_id"])
        op.create_index("ix_contact_permissions_payment_attempt_id", "contact_permissions", ["payment_attempt_id"])
        op.create_index("ix_contact_permissions_address_fingerprint", "contact_permissions", ["address_fingerprint"])
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_contact_permission_active
            ON contact_permissions (seller_id, channel, contact_subject_id, purpose, scope_type, payment_attempt_id)
            WHERE status='active'
            """
        )

    # ── ContactSuppression ──
    if not _has_table("contact_suppressions"):
        op.create_table(
            "contact_suppressions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("channel", sa.String(length=20), nullable=False, server_default="whatsapp"),
            sa.Column("contact_subject_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contact_subjects.id"), nullable=False),
            sa.Column("address_fingerprint", sa.String(length=255), nullable=False),
            sa.Column("fingerprint_key_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("purpose", sa.String(length=50), nullable=False, server_default="transactional_payment_reminder"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("source_event", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("lifted_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_contact_suppressions_seller_id", "contact_suppressions", ["seller_id"])
        op.create_index("ix_contact_suppressions_contact_subject_id", "contact_suppressions", ["contact_subject_id"])
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_contact_suppression_active
            ON contact_suppressions (seller_id, channel, contact_subject_id, purpose)
            WHERE status='active'
            """
        )

    # ── RevenueOpportunity ──
    if not _has_table("revenue_opportunities"):
        op.create_table(
            "revenue_opportunities",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
            sa.Column("payment_attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payment_attempts.id"), nullable=False),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("opportunity_type", sa.String(length=50), nullable=False, server_default="pending_payment_recovery"),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="detected"),
            sa.Column("signal_key", sa.String(length=255), nullable=False),
            sa.Column("amount_snapshot", sa.Numeric(precision=18, scale=2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="IDR"),
            sa.Column("evidence_json", sa.JSON(), server_default=sa.text("'{}'::json")),
            sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("eligible_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("suppression_code", sa.String(length=50), nullable=True),
            sa.Column("terminal_reason_code", sa.String(length=50), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        )
        op.create_index("ix_revenue_opportunities_seller_id", "revenue_opportunities", ["seller_id"])
        op.create_index("ix_revenue_opportunities_order_id", "revenue_opportunities", ["order_id"])
        op.create_index("ix_revenue_opportunities_status", "revenue_opportunities", ["status"])
        op.create_unique_constraint("uq_revenue_opportunity_signal_key", "revenue_opportunities", ["signal_key"])

    # ── OutboundDispatch ──
    if not _has_table("outbound_dispatches"):
        op.create_table(
            "outbound_dispatches",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_opportunities.id"), nullable=False),
            sa.Column("approval_id", sa.Integer(), sa.ForeignKey("agent_approvals.id"), nullable=True),
            sa.Column("background_job_id", sa.Integer(), sa.ForeignKey("background_jobs.id"), nullable=True),
            sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id"), nullable=True),
            sa.Column("channel_type", sa.String(length=20), nullable=False, server_default="whatsapp"),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("delivery_status", sa.String(length=20), nullable=False, server_default="not_available"),
            sa.Column("template_code", sa.String(length=100), nullable=False),
            sa.Column("template_params_json", sa.JSON(), server_default=sa.text("'{}'::json")),
            sa.Column("action_digest", sa.String(length=64), nullable=False),
            sa.Column("contact_permission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contact_permissions.id"), nullable=False),
            sa.Column("contact_subject_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contact_subjects.id"), nullable=False),
            sa.Column("recipient_fingerprint", sa.String(length=255), nullable=False),
            sa.Column("idempotency_key", sa.String(length=255), nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False, server_default="whatsapp_cloud"),
            sa.Column("provider_request_id", sa.String(length=255), nullable=True),
            sa.Column("provider_message_id", sa.String(length=255), nullable=True),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error_code", sa.String(length=100), nullable=True),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("delivery_failed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        )
        op.create_index("ix_outbound_dispatches_seller_id", "outbound_dispatches", ["seller_id"])
        op.create_index("ix_outbound_dispatches_opportunity_id", "outbound_dispatches", ["opportunity_id"])
        op.create_index("ix_outbound_dispatches_status", "outbound_dispatches", ["status"])
        op.create_unique_constraint("uq_dispatch_opportunity", "outbound_dispatches", ["opportunity_id"])
        op.create_unique_constraint("uq_dispatch_idempotency_key", "outbound_dispatches", ["idempotency_key"])
        op.create_index("ix_dispatch_provider_message", "outbound_dispatches", ["provider", "channel_id", "provider_message_id"])

    # ── OutcomeEvent ──
    if not _has_table("outcome_events"):
        op.create_table(
            "outcome_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
            sa.Column("payment_attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payment_attempts.id"), nullable=False),
            sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_opportunities.id"), nullable=False),
            sa.Column("dispatch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outbound_dispatches.id"), nullable=True),
            sa.Column("event_type", sa.String(length=30), nullable=False),
            sa.Column("source_event_key", sa.String(length=255), nullable=False),
            sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="IDR"),
            sa.Column("reversal_of_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outcome_events.id"), nullable=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("evidence_json", sa.JSON(), server_default=sa.text("'{}'::json")),
        )
        op.create_index("ix_outcome_events_seller_id", "outcome_events", ["seller_id"])
        op.create_index("ix_outcome_events_order_id", "outcome_events", ["order_id"])
        op.create_unique_constraint("uq_outcome_source_event_key", "outcome_events", ["source_event_key"])

    # ── AttributionAssessment ──
    if not _has_table("attribution_assessments"):
        op.create_table(
            "attribution_assessments",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("outcome_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outcome_events.id"), nullable=False),
            sa.Column("method", sa.String(length=30), nullable=False),
            sa.Column("rule_version", sa.String(length=50), nullable=True),
            sa.Column("experiment_id", sa.String(length=100), nullable=True),
            sa.Column("assessed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
            sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column("estimate", sa.Numeric(precision=18, scale=2), nullable=True),
            sa.Column("confidence", sa.String(length=50), nullable=True),
            sa.Column("evidence_json", sa.JSON(), server_default=sa.text("'{}'::json")),
        )
        op.create_index("ix_attribution_assessments_seller_id", "attribution_assessments", ["seller_id"])
        op.create_index("ix_attribution_assessments_outcome_event_id", "attribution_assessments", ["outcome_event_id"])
        op.create_unique_constraint(
            "uq_attribution_outcome_method_rule", "attribution_assessments",
            ["outcome_event_id", "method", "rule_version"],
        )

    # ── RecipientContactWindow ──
    if not _has_table("recipient_contact_windows"):
        op.create_table(
            "recipient_contact_windows",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("contact_subject_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contact_subjects.id"), nullable=False),
            sa.Column("purpose", sa.String(length=50), nullable=False, server_default="transactional_payment_reminder"),
            sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_opportunities.id"), nullable=False),
            sa.Column("dispatch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outbound_dispatches.id"), nullable=True),
            sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("window_ends_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="reserved"),
            sa.Column("reserved_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("release_reason", sa.String(length=50), nullable=True),
        )
        op.create_index("ix_recipient_contact_windows_seller_id", "recipient_contact_windows", ["seller_id"])
        op.create_index("ix_contact_window_seller_subject_purpose", "recipient_contact_windows", ["seller_id", "contact_subject_id", "purpose"])

    # ── AgentApproval extension columns (nullable for legacy compatibility) ──
    if not _has_column("agent_approvals", "opportunity_id"):
        op.add_column("agent_approvals", sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), nullable=True))
    if not _has_column("agent_approvals", "action_digest"):
        op.add_column("agent_approvals", sa.Column("action_digest", sa.String(length=64), nullable=True))
    if not _has_column("agent_approvals", "action_revision"):
        op.add_column("agent_approvals", sa.Column("action_revision", sa.Integer(), nullable=True))
    if not _has_column("agent_approvals", "policy_version"):
        op.add_column("agent_approvals", sa.Column("policy_version", sa.Integer(), nullable=True))
    if not _has_column("agent_approvals", "expected_state_version"):
        op.add_column("agent_approvals", sa.Column("expected_state_version", sa.Integer(), nullable=True))
    if not _has_column("agent_approvals", "expires_at"):
        op.add_column("agent_approvals", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    if not _has_column("agent_approvals", "used_at"):
        op.add_column("agent_approvals", sa.Column("used_at", sa.DateTime(timezone=True), nullable=True))
    if not _has_column("agent_approvals", "decided_via"):
        op.add_column("agent_approvals", sa.Column("decided_via", sa.String(length=50), nullable=True))
    if not _has_column("agent_approvals", "decision_idempotency_key"):
        op.add_column("agent_approvals", sa.Column("decision_idempotency_key", sa.String(length=255), nullable=True))
    if not _has_column("agent_approvals", "decision_request_hash"):
        op.add_column("agent_approvals", sa.Column("decision_request_hash", sa.String(length=64), nullable=True))
    if not _has_column("agent_approvals", "decision_scope"):
        op.add_column("agent_approvals", sa.Column("decision_scope", sa.String(length=100), nullable=True))
    if not _has_column("agent_approvals", "decision_response_json"):
        op.add_column("agent_approvals", sa.Column("decision_response_json", sa.JSON(), nullable=True))
    if not _has_column("agent_approvals", "approval_token_hash"):
        op.add_column("agent_approvals", sa.Column("approval_token_hash", sa.String(length=64), nullable=True))

    if not _has_index("agent_approvals", "ix_agent_approvals_opportunity_id"):
        op.create_index("ix_agent_approvals_opportunity_id", "agent_approvals", ["opportunity_id"])

    # Partial unique: one current pending recovery approval per opportunity
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_one_pending_recovery_per_opportunity
        ON agent_approvals (opportunity_id)
        WHERE opportunity_id IS NOT NULL AND status='pending'
        """
    )
    # Unique scoped receipt for non-null idempotency key
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_approval_scoped_receipt
        ON agent_approvals (seller_id, decision_scope, opportunity_id, decision_idempotency_key)
        WHERE decision_idempotency_key IS NOT NULL
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_approval_scoped_receipt")
    op.execute("DROP INDEX IF EXISTS uq_one_pending_recovery_per_opportunity")
    if _has_index("agent_approvals", "ix_agent_approvals_opportunity_id"):
        op.drop_index("ix_agent_approvals_opportunity_id", table_name="agent_approvals")
    for col in ["approval_token_hash", "decision_response_json", "decision_scope", "decision_request_hash",
                "decision_idempotency_key", "decided_via", "used_at", "expires_at",
                "expected_state_version", "policy_version", "action_revision", "action_digest", "opportunity_id"]:
        if _has_column("agent_approvals", col):
            op.drop_column("agent_approvals", col)

    if _has_table("recipient_contact_windows"):
        if _has_index("recipient_contact_windows", "ix_contact_window_seller_subject_purpose"):
            op.drop_index("ix_contact_window_seller_subject_purpose", table_name="recipient_contact_windows")
        if _has_index("recipient_contact_windows", "ix_recipient_contact_windows_seller_id"):
            op.drop_index("ix_recipient_contact_windows_seller_id", table_name="recipient_contact_windows")
        op.drop_table("recipient_contact_windows")

    if _has_table("attribution_assessments"):
        if _has_index("attribution_assessments", "ix_attribution_assessments_outcome_event_id"):
            op.drop_index("ix_attribution_assessments_outcome_event_id", table_name="attribution_assessments")
        if _has_index("attribution_assessments", "ix_attribution_assessments_seller_id"):
            op.drop_index("ix_attribution_assessments_seller_id", table_name="attribution_assessments")
        op.drop_table("attribution_assessments")

    if _has_table("outcome_events"):
        if _has_index("outcome_events", "ix_outcome_events_order_id"):
            op.drop_index("ix_outcome_events_order_id", table_name="outcome_events")
        if _has_index("outcome_events", "ix_outcome_events_seller_id"):
            op.drop_index("ix_outcome_events_seller_id", table_name="outcome_events")
        op.drop_table("outcome_events")

    if _has_table("outbound_dispatches"):
        if _has_index("outbound_dispatches", "ix_dispatch_provider_message"):
            op.drop_index("ix_dispatch_provider_message", table_name="outbound_dispatches")
        if _has_index("outbound_dispatches", "ix_outbound_dispatches_status"):
            op.drop_index("ix_outbound_dispatches_status", table_name="outbound_dispatches")
        if _has_index("outbound_dispatches", "ix_outbound_dispatches_opportunity_id"):
            op.drop_index("ix_outbound_dispatches_opportunity_id", table_name="outbound_dispatches")
        if _has_index("outbound_dispatches", "ix_outbound_dispatches_seller_id"):
            op.drop_index("ix_outbound_dispatches_seller_id", table_name="outbound_dispatches")
        op.drop_table("outbound_dispatches")

    if _has_table("revenue_opportunities"):
        if _has_index("revenue_opportunities", "ix_revenue_opportunities_status"):
            op.drop_index("ix_revenue_opportunities_status", table_name="revenue_opportunities")
        if _has_index("revenue_opportunities", "ix_revenue_opportunities_order_id"):
            op.drop_index("ix_revenue_opportunities_order_id", table_name="revenue_opportunities")
        if _has_index("revenue_opportunities", "ix_revenue_opportunities_seller_id"):
            op.drop_index("ix_revenue_opportunities_seller_id", table_name="revenue_opportunities")
        op.drop_table("revenue_opportunities")

    if _has_table("contact_suppressions"):
        op.execute("DROP INDEX IF EXISTS uq_contact_suppression_active")
        if _has_index("contact_suppressions", "ix_contact_suppressions_contact_subject_id"):
            op.drop_index("ix_contact_suppressions_contact_subject_id", table_name="contact_suppressions")
        if _has_index("contact_suppressions", "ix_contact_suppressions_seller_id"):
            op.drop_index("ix_contact_suppressions_seller_id", table_name="contact_suppressions")
        op.drop_table("contact_suppressions")

    if _has_table("contact_permissions"):
        op.execute("DROP INDEX IF EXISTS uq_contact_permission_active")
        for idx in ["ix_contact_permissions_address_fingerprint", "ix_contact_permissions_payment_attempt_id",
                    "ix_contact_permissions_order_id", "ix_contact_permissions_contact_subject_id",
                    "ix_contact_permissions_seller_id"]:
            if _has_index("contact_permissions", idx):
                op.drop_index(idx, table_name="contact_permissions")
        op.drop_table("contact_permissions")

    if _has_table("contact_subject_fingerprints"):
        op.drop_table("contact_subject_fingerprints")
    if _has_table("contact_subjects"):
        for idx in ["ix_contact_subject_seller_channel", "ix_contact_subjects_customer_id", "ix_contact_subjects_seller_id"]:
            if _has_index("contact_subjects", idx):
                op.drop_index(idx, table_name="contact_subjects")
        op.drop_table("contact_subjects")

    if _has_table("payment_recovery_controls"):
        op.drop_table("payment_recovery_controls")

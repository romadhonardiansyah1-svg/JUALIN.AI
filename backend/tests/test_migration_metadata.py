import unittest

from models.agent_os import AgentApproval
from models.ai_quality import AITrace
from models.auth_session import AuthSession
from models.billing import UsageCounter
from models.inbox import InboxMessage, InboxThread
from models.order import Order
from models.scale_core import BackgroundJob


class MigrationMetadataTests(unittest.TestCase):
    def test_performance_indexes_are_declared_in_orm_metadata(self):
        expected_indexes = {
            AITrace: 'ix_ai_traces_seller_status',
            AuthSession: 'ix_auth_sessions_actor_user_id',
            BackgroundJob: 'ix_jobs_status_next_run',
            InboxMessage: 'ix_inbox_messages_thread_created',
            InboxThread: 'ix_inbox_threads_seller_lastmsg',
            Order: 'ix_orders_seller_status_created',
            UsageCounter: 'ix_usage_counters_seller_metric_period',
        }

        for model, expected_name in expected_indexes.items():
            with self.subTest(model=model.__name__):
                index_names = {index.name for index in model.__table__.indexes}
                self.assertIn(expected_name, index_names)

    def test_partial_indexes_are_declared_in_orm_metadata(self):
        expected_indexes = {
            BackgroundJob: {
                "ix_jobs_queued_processable": (
                    ("next_run_at", "id"),
                    False,
                    "status = 'queued' AND execution_stage = 'pre_side_effect'",
                ),
            },
            AgentApproval: {
                "uq_one_pending_recovery_per_opportunity": (
                    ("opportunity_id",),
                    True,
                    "opportunity_id IS NOT NULL AND status='pending'",
                ),
                "uq_approval_scoped_receipt": (
                    (
                        "seller_id",
                        "decision_scope",
                        "opportunity_id",
                        "decision_idempotency_key",
                    ),
                    True,
                    "decision_idempotency_key IS NOT NULL",
                ),
            },
        }

        for model, expected in expected_indexes.items():
            indexes = {index.name: index for index in model.__table__.indexes}
            for name, (columns, unique, predicate) in expected.items():
                with self.subTest(model=model.__name__, index=name):
                    self.assertIn(name, indexes)
                    index = indexes[name]
                    self.assertEqual(
                        columns,
                        tuple(column.name for column in index.columns),
                    )
                    self.assertEqual(unique, index.unique)
                    self.assertEqual(
                        predicate,
                        str(index.dialect_options["postgresql"]["where"]),
                    )

    def test_only_disposable_guard_sentinel_is_excluded_from_autogenerate(self):
        from alembic_policy import include_object

        self.assertFalse(
            include_object(
                None,
                "disposable_db_sentinel",
                "table",
                reflected=True,
                compare_to=None,
            )
        )
        self.assertTrue(
            include_object(
                None,
                "unexpected_table",
                "table",
                reflected=True,
                compare_to=None,
            )
        )


if __name__ == '__main__':
    unittest.main()

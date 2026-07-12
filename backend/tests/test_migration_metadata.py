import unittest

from models.ai_quality import AITrace
from models.billing import UsageCounter
from models.inbox import InboxMessage, InboxThread
from models.order import Order
from models.scale_core import BackgroundJob


class MigrationMetadataTests(unittest.TestCase):
    def test_performance_indexes_are_declared_in_orm_metadata(self):
        expected_indexes = {
            AITrace: 'ix_ai_traces_seller_status',
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


if __name__ == '__main__':
    unittest.main()

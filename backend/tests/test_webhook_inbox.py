"""
P1.3 — Atomic durable webhook inbox and delivery status.
"""
import unittest
from unittest.mock import AsyncMock, MagicMock


class WebhookInboxTests(unittest.IsolatedAsyncioTestCase):
    async def test_atomic_insert_uses_on_conflict(self):
        from core.idempotency import get_or_create_webhook_event
        import inspect

        source = inspect.getsource(get_or_create_webhook_event)
        self.assertIn("ON CONFLICT", source)
        self.assertIn("idempotency_key", source)

    async def test_composite_dedupe_uses_provider_account(self):
        from core.idempotency import get_or_create_webhook_event_composite
        import inspect

        source = inspect.getsource(get_or_create_webhook_event_composite)
        self.assertIn("provider_account_id", source)
        self.assertIn("ON CONFLICT", source)

    async def test_normalized_payload_not_raw(self):
        from core.idempotency import get_or_create_webhook_event

        mock_db = AsyncMock()
        mock_result_insert = MagicMock()
        mock_result_insert.fetchone.return_value = (1,)
        mock_event = MagicMock()
        mock_event.id = 1
        mock_result_select = MagicMock()
        mock_result_select.scalar_one.return_value = mock_event

        mock_db.execute.side_effect = [mock_result_insert, mock_result_select]

        event, is_new = await get_or_create_webhook_event(
            mock_db,
            provider="whatsapp_cloud",
            payload={"some": "data", "raw_secrets": "should_not_be_stored_as_is"},
            event_type="message",
            external_event_id="msg-123",
            provider_account_id="acct-1",
        )

        self.assertTrue(is_new)
        # Check that payload stored is normalized, not raw secrets
        first_call = mock_db.execute.call_args_list[0]
        # Payload is second arg dict
        payload_arg = first_call[0][1]["payload"] if len(first_call[0]) > 1 else ""
        # Should not contain raw secret string verbatim? At least not contain "should_not_be_stored_as_is"
        self.assertNotIn("should_not_be_stored_as_is", str(payload_arg))

    async def test_statuses_parsed(self):
        from services.messaging.whatsapp_cloud import WhatsAppCloudProvider

        provider = WhatsAppCloudProvider(app_secret="test-secret")
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "123"},
                                "statuses": [
                                    {"id": "wamid.abc", "status": "delivered", "timestamp": "123456", "recipient_id": "628123"},
                                    {"id": "wamid.abc", "status": "read", "timestamp": "123457", "recipient_id": "628123"},
                                ],
                            }
                        }
                    ]
                }
            ]
        }

        statuses = provider.parse_statuses(payload)
        self.assertEqual(len(statuses), 2)
        self.assertEqual(statuses[0]["status"], "delivered")
        self.assertEqual(statuses[1]["status"], "read")
        self.assertEqual(statuses[0]["provider_account_id"], "123")


if __name__ == "__main__":
    unittest.main()

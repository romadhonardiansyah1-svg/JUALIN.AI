"""P4.4 — WhatsApp utility template send/sync contract tests."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from services.messaging.whatsapp_cloud import WhatsAppCloudProvider
from services.messaging.base import SendMessageResult


class TemplateValidationTests(unittest.TestCase):
    def test_rejects_invalid_name_language_and_count(self):
        self.assertEqual(
            WhatsAppCloudProvider.validate_template_send(
                template_name="Bad Name",
                language_code="id",
                body_parameters=[],
                expected_parameter_count=0,
            ),
            "invalid_template_name",
        )
        self.assertEqual(
            WhatsAppCloudProvider.validate_template_send(
                template_name="payment_reminder_v1",
                language_code="indonesia",
                body_parameters=[],
                expected_parameter_count=0,
            ),
            "invalid_template_language",
        )
        self.assertEqual(
            WhatsAppCloudProvider.validate_template_send(
                template_name="payment_reminder_v1",
                language_code="id",
                body_parameters=["a"],
                expected_parameter_count=2,
            ),
            "template_parameter_count_mismatch",
        )
        self.assertIsNone(
            WhatsAppCloudProvider.validate_template_send(
                template_name="payment_reminder_v1",
                language_code="id",
                body_parameters=["a", "b"],
                expected_parameter_count=2,
            )
        )


class TemplateSendTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_template_posts_template_payload(self):
        provider = WhatsAppCloudProvider(
            access_token="token",
            phone_number_id="pnid",
        )
        response = MagicMock()
        response.is_success = True
        response.text = '{"messages":[{"id":"wamid.tpl1"}]}'
        response.json.return_value = {"messages": [{"id": "wamid.tpl1"}]}

        mock_client = AsyncMock()
        mock_client.post.return_value = response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("services.messaging.whatsapp_cloud.httpx.AsyncClient", return_value=mock_client):
            result = await provider.send_template(
                "+6281234567890",
                template_name="payment_reminder_v1",
                language_code="id",
                body_parameters=["ORD-1", "125000"],
                expected_parameter_count=2,
            )

        self.assertEqual(result.outcome, "accepted")
        self.assertEqual(result.provider_message_id, "wamid.tpl1")
        kwargs = mock_client.post.await_args.kwargs
        body = kwargs["json"]
        self.assertEqual(body["type"], "template")
        self.assertEqual(body["template"]["name"], "payment_reminder_v1")
        self.assertEqual(len(body["template"]["components"][0]["parameters"]), 2)

    async def test_invalid_params_are_rejected_without_network(self):
        provider = WhatsAppCloudProvider(access_token="token", phone_number_id="pnid")
        with patch("services.messaging.whatsapp_cloud.httpx.AsyncClient") as client_cls:
            result = await provider.send_template(
                "+6281234567890",
                template_name="NOT VALID",
                language_code="id",
            )
        self.assertEqual(result.outcome, "rejected")
        self.assertEqual(result.error_message, "invalid_template_name")
        client_cls.assert_not_called()

    async def test_sync_without_waba_is_honest_failure(self):
        provider = WhatsAppCloudProvider(access_token="token", phone_number_id="pnid", waba_id="")
        result = await provider.sync_message_templates()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "provider_credentials_unavailable")
        self.assertEqual(result["templates"], [])


if __name__ == "__main__":
    unittest.main()

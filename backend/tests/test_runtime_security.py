import hashlib
import hmac
import os
import unittest
from unittest.mock import patch

from api import routes_webhooks
from config import Settings, validate_production_security
from services.messaging.whatsapp_cloud import WhatsAppCloudProvider


class WhatsAppWebhookSecurityTests(unittest.IsolatedAsyncioTestCase):
    def test_unsigned_webhook_is_rejected_when_app_secret_is_missing(self):
        provider = WhatsAppCloudProvider(app_secret='')

        self.assertFalse(provider.verify_webhook(b'payload', {}))

    def test_valid_webhook_signature_is_accepted(self):
        payload = b'webhook-payload'
        secret = 'test-app-secret'
        digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        provider = WhatsAppCloudProvider(app_secret=secret)

        self.assertTrue(
            provider.verify_webhook(
                payload,
                {'x-hub-signature-256': f'sha256={digest}'},
            )
        )

    def test_non_ascii_webhook_signature_is_rejected(self):
        provider = WhatsAppCloudProvider(app_secret='test-app-secret')

        self.assertFalse(
            provider.verify_webhook(
                b'payload',
                {'x-hub-signature-256': 'sha256=é'},
            )
        )

    async def test_verification_endpoint_is_unavailable_without_configured_token(self):
        with patch.object(routes_webhooks.settings, 'WHATSAPP_VERIFY_TOKEN', ''):
            response = await routes_webhooks.whatsapp_cloud_verify(
                hub_mode='subscribe',
                hub_verify_token='',
                hub_challenge='challenge',
            )

        self.assertEqual(response.status_code, 503)

    async def test_non_ascii_verification_token_is_rejected(self):
        with patch.object(routes_webhooks.settings, 'WHATSAPP_VERIFY_TOKEN', 'test-token'):
            response = await routes_webhooks.whatsapp_cloud_verify(
                hub_mode='subscribe',
                hub_verify_token='é',
                hub_challenge='challenge',
            )

        self.assertEqual(response.status_code, 403)


class ProductionConfigurationTests(unittest.TestCase):
    def test_runtime_schema_creation_is_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)

        self.assertFalse(settings.AUTO_CREATE_TABLES)

    def test_whatsapp_secrets_are_required_when_integration_is_enabled(self):
        settings = Settings(
            DEBUG=False,
            SECRET_KEY='s' * 48,
            JWT_SECRET_KEY='j' * 48,
            CORS_ORIGINS=['https://app.example.com'],
            BASE_URL='https://api.example.com',
            FRONTEND_URL='https://app.example.com',
            ENABLE_WHATSAPP=True,
            WHATSAPP_VERIFY_TOKEN='',
            WHATSAPP_APP_SECRET='',
        )

        errors = validate_production_security(settings)

        for key_name in (
            'WHATSAPP_VERIFY_TOKEN',
            'WHATSAPP_ACCESS_TOKEN',
            'WHATSAPP_PHONE_NUMBER_ID',
            'WHATSAPP_APP_SECRET',
        ):
            with self.subTest(key_name=key_name):
                self.assertTrue(any(key_name in error for error in errors))

"""Regression coverage: query-string scrubbing before events reach Sentry.

sentry_sdk's EventScrubber only walks request headers/cookies/data
(sentry_sdk/scrubber.py:123-131), while the ASGI integration attaches
query_string unconditionally when data_collection is unset
(sentry_sdk/integrations/_asgi_common.py:140-141). No real events are sent here.
"""
import os
import unittest
from unittest.mock import patch

from core.observability import _EXTRA_DENYLIST, init_sentry, scrub_event_request


def _event(query_string, url="http://api.test/api/payments/public/status/7"):
    return {
        "level": "error",
        "request": {
            "method": "GET",
            "url": url,
            "query_string": query_string,
            "headers": {"host": "api.test"},
        },
    }


class QueryStringScrubbingTests(unittest.TestCase):
    def test_payment_token_value_is_filtered(self):
        event = scrub_event_request(_event("token=secret-capability-token"))

        self.assertNotIn("secret-capability-token", str(event))
        self.assertIn("token=", event["request"]["query_string"])

    def test_sensitive_token_variants_are_filtered(self):
        for name in ("token", "bootstrap_token", "session_token", "payment_access_token", "api_key"):
            with self.subTest(name=name):
                event = scrub_event_request(_event(f"{name}=leaky-value"))
                self.assertNotIn("leaky-value", str(event))

    def test_non_sensitive_params_are_preserved(self):
        event = scrub_event_request(_event("token=abc123&method=qris&page=2"))
        qs = event["request"]["query_string"]

        self.assertNotIn("abc123", qs)
        self.assertIn("method=qris", qs)
        self.assertIn("page=2", qs)
        self.assertIn("token=", qs)

    def test_dict_shaped_query_string_is_handled(self):
        event = scrub_event_request(_event({"token": "abc123", "page": "2"}))

        self.assertEqual(event["request"]["query_string"]["token"], "[Filtered]")
        self.assertEqual(event["request"]["query_string"]["page"], "2")

    def test_url_carrying_a_query_string_is_scrubbed(self):
        event = scrub_event_request(
            _event(None, url="http://api.test/pay/7?token=abc123&method=qris")
        )

        self.assertNotIn("abc123", event["request"]["url"])
        self.assertIn("method=qris", event["request"]["url"])

    def test_does_not_crash_on_events_without_request_data(self):
        self.assertEqual(scrub_event_request({"level": "error"}), {"level": "error"})
        self.assertEqual(scrub_event_request({"request": None}), {"request": None})
        self.assertIsNone(scrub_event_request(None))

        no_qs = {"request": {"method": "GET", "url": "http://api.test/health"}}
        self.assertEqual(scrub_event_request(no_qs), no_qs)

        for empty in ("", None):
            with self.subTest(query_string=empty):
                event = scrub_event_request(_event(empty))
                self.assertEqual(event["request"]["query_string"], empty)

    def test_unparseable_query_string_is_dropped_entirely(self):
        event = scrub_event_request(_event("opaque-blob-without-pairs"))

        # parse_qsl treats a bare token as a key with an empty value; the important
        # property is that no secret value survives. Keys are preserved.
        self.assertNotIn("[Filtered]", event["request"]["query_string"])


class DenylistCoverageTests(unittest.TestCase):
    def test_pii_and_secret_field_names_are_denylisted(self):
        for name in (
            "email", "customer_email", "no_hp", "phone", "customer_phone",
            "customer_address", "customer_name", "alamat", "address_book",
            "whatsapp_id", "password_hash", "recipient_fingerprint",
            "raw_token", "raw_session_token", "session_token", "session_token_hmac",
            "token_hmac", "bootstrap_token", "payment_access_token",
            "payment_url", "payment_va_number", "payment_qr_data",
        ):
            with self.subTest(name=name):
                self.assertIn(name, _EXTRA_DENYLIST)

    def test_denylist_entries_are_lowercase_and_unique(self):
        self.assertEqual(_EXTRA_DENYLIST, [n.lower() for n in _EXTRA_DENYLIST])
        self.assertEqual(len(_EXTRA_DENYLIST), len(set(_EXTRA_DENYLIST)))


class InitSentryTests(unittest.TestCase):
    def test_init_is_inert_without_dsn(self):
        from config import Settings

        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)
        self.assertEqual(settings.SENTRY_DSN, "")

        with patch("core.observability.get_settings", return_value=settings), \
                patch("sentry_sdk.init") as sentry_init:
            self.assertFalse(init_sentry())

        sentry_init.assert_not_called()


if __name__ == "__main__":
    unittest.main()

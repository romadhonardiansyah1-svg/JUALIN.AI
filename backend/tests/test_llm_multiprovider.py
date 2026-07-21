"""Regression: multi-provider failover order and config resolution."""
import unittest
from types import SimpleNamespace

from services.llm_router import (
    _attempts,
    _provider_from_row,
    _provider_from_singleton,
    _env_provider,
)


def _prov(**kw):
    base = dict(base_url="http://x/v1", model="m", light_model="", fallback_model="", api_keys=["k1"])
    base.update(kw)
    return SimpleNamespace(**base)


class MultiProviderRoutingTests(unittest.TestCase):
    def test_attempts_order_providers_then_keys_then_fallback(self):
        providers = [
            _prov(base_url="http://a/v1", model="a-main", fallback_model="a-fb", api_keys=["ka1", "ka2"]),
            _prov(base_url="http://b/v1", model="b-main", api_keys=["kb1"]),
        ]
        got = list(_attempts(providers, "main"))
        self.assertEqual(
            got,
            [
                ("http://a/v1", "ka1", "a-main"),
                ("http://a/v1", "ka2", "a-main"),
                ("http://a/v1", "ka1", "a-fb"),
                ("http://a/v1", "ka2", "a-fb"),
                ("http://b/v1", "kb1", "b-main"),
            ],
        )

    def test_attempts_light_purpose_prefers_light_model(self):
        providers = [_prov(model="main", light_model="light", api_keys=["k"])]
        got = list(_attempts(providers, "light"))
        self.assertEqual(got, [("http://x/v1", "k", "light")])

    def test_attempts_light_falls_back_to_main_when_no_light(self):
        providers = [_prov(model="main", light_model="", api_keys=["k"])]
        got = list(_attempts(providers, "light"))
        self.assertEqual(got, [("http://x/v1", "k", "main")])

    def test_provider_from_row_uses_keys_and_label(self):
        row = SimpleNamespace(
            id=7, label="Groq", base_url="https://api.groq.com/openai/v1",
            model="llama-3.3-70b-versatile", light_model="", fallback_model="",
            api_keys_json=["gsk_a", "", "gsk_b"],
        )
        p = _provider_from_row(row)
        self.assertEqual(p.base_url, "https://api.groq.com/openai/v1")
        self.assertEqual(p.api_keys, ["gsk_a", "gsk_b"])  # empties filtered
        self.assertEqual(p.label, "Groq")

    def test_provider_from_singleton_falls_back_to_env_key_when_empty(self):
        row = SimpleNamespace(
            provider_label="", base_url="", model="", light_model="", fallback_model="",
            api_keys_json=[],
        )
        p = _provider_from_singleton(row)
        # empty base_url/model should fall back to env config, and at least one key present
        self.assertTrue(p.api_keys)
        self.assertTrue(p.base_url)

    def test_env_provider_is_single_and_labeled(self):
        p = _env_provider()
        self.assertEqual(p.label, "env")
        self.assertTrue(p.api_keys)


if __name__ == "__main__":
    unittest.main()

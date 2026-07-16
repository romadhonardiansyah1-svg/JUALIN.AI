"""P5.3 — Bounded recovery AI template selection."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from services.payment_recovery.ai_copy import (
    STATIC_BASELINE_VARIANT,
    parse_model_selection,
    render_variant,
    select_recovery_template_variant,
    select_static,
)


class ParseAndRenderTests(unittest.TestCase):
    def test_parse_accepts_allowlisted_json_only(self):
        self.assertEqual(
            parse_model_selection('{"variant_id":"payment_reminder_clear_v1"}'),
            "payment_reminder_clear_v1",
        )
        self.assertIsNone(parse_model_selection("payment_reminder_clear_v1"))
        self.assertIsNone(parse_model_selection('{"variant_id":"not_real"}'))
        self.assertIsNone(
            parse_model_selection(
                '{"variant_id":"payment_reminder_clear_v1","discount":"50%"}'
            )
        )
        self.assertIsNone(
            parse_model_selection(
                '{"variant_id":"payment_reminder_clear_v1","payment_url":"https://evil"}'
            )
        )

    def test_render_fills_only_approved_placeholders(self):
        text = render_variant(
            "payment_reminder_soft_v1",
            {"order_ref": "ORD-9", "amount_display": "Rp125.000"},
        )
        self.assertIn("ORD-9", text)
        self.assertIn("Rp125.000", text)
        self.assertNotIn("{{", text)
        self.assertNotIn("https://", text)

    def test_static_baseline_ok(self):
        result = select_static({"order_ref": "ORD-1", "amount_display": "Rp10.000"})
        self.assertTrue(result.ok)
        self.assertEqual(result.variant_id, STATIC_BASELINE_VARIANT)
        self.assertEqual(result.source, "static")


class SelectionAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_ai_disabled_uses_static(self):
        result = await select_recovery_template_variant(
            {"order_ref": "ORD-1", "amount_display": "Rp10.000"},
            allow_ai=False,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.source, "static")
        self.assertEqual(result.reason, "ai_disabled")

    async def test_prompt_injection_payload_rejected(self):
        with patch(
            "services.llm_router.llm_chat",
            new=AsyncMock(
                return_value='{"variant_id":"payment_reminder_soft_v1","send":true,"recipient":"+628"}'
            ),
        ):
            result = await select_recovery_template_variant(
                {"order_ref": "ORD-1", "amount_display": "Rp10.000"},
                allow_ai=True,
                fallback="no_send",
            )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "invalid_or_forbidden_schema")

    async def test_fabricated_discount_schema_rejected_falls_back_static(self):
        with patch(
            "services.llm_router.llm_chat",
            new=AsyncMock(return_value='{"variant_id":"x","discount":"99%"}'),
        ):
            result = await select_recovery_template_variant(
                {"order_ref": "ORD-1", "amount_display": "Rp10.000"},
                allow_ai=True,
                fallback="static",
            )
        self.assertTrue(result.ok)
        self.assertEqual(result.source, "static")
        self.assertEqual(result.reason, "invalid_ai_static_fallback")

    async def test_valid_ai_selection(self):
        with patch(
            "services.llm_router.llm_chat",
            new=AsyncMock(return_value='{"variant_id":"payment_reminder_clear_v1"}'),
        ):
            result = await select_recovery_template_variant(
                {"order_ref": "ORD-2", "amount_display": "Rp20.000"},
                allow_ai=True,
            )
        self.assertTrue(result.ok)
        self.assertEqual(result.source, "ai")
        self.assertEqual(result.variant_id, "payment_reminder_clear_v1")
        self.assertIn("ORD-2", result.rendered_preview)

    async def test_timeout_no_send(self):
        with patch(
            "services.llm_router.llm_chat",
            new=AsyncMock(side_effect=TimeoutError("timeout")),
        ):
            result = await select_recovery_template_variant(
                {"order_ref": "ORD-1", "amount_display": "Rp10.000"},
                allow_ai=True,
                fallback="no_send",
            )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "ai_timeout_or_error")


if __name__ == "__main__":
    unittest.main()

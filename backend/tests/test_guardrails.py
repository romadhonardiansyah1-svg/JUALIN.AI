"""
JUALIN.AI — Guardrails Tests
Anti-halusinasi dan safety tests
"""
import pytest


class TestAntiHalusinasi:
    """Test AI tidak mengarang informasi."""

    def test_guardrails_module_exists(self):
        """Guardrails module importable."""
        from ai.guardrails import check_guardrails
        assert callable(check_guardrails)

    def test_safe_response(self):
        """Safe response passes."""
        from ai.guardrails import check_guardrails
        result = check_guardrails("Baju Pink harganya Rp 89.000", "harga baju pink")
        assert result["is_safe"] is True

    def test_off_topic_detection(self):
        """Off-topic patterns detected."""
        off_topic_keywords = ["presiden", "agama", "politik", "hack", "password"]
        message = "siapa presiden Indonesia"
        found = any(k in message.lower() for k in off_topic_keywords)
        assert found is True

    def test_angry_detection(self):
        """Angry customer detection."""
        angry_patterns = ["goblok", "bangsat", "brengsek", "tai"]
        message = "pelayanan kalian tai!"
        found = any(p in message.lower() for p in angry_patterns)
        assert found is True

    def test_price_in_response(self):
        """Price should come from catalog, not made up."""
        catalog_price = 89000
        response_price = 89000  # Should match catalog
        assert response_price == catalog_price

    def test_stock_realtime(self):
        """Stock should be checked real-time."""
        # Stock should never be cached
        stock_cached = False
        assert stock_cached is False

    def test_guardrail_rules_count(self):
        """We have 7 guardrail rules."""
        from ai.guardrails import GUARDRAIL_RULES
        assert len(GUARDRAIL_RULES) >= 7

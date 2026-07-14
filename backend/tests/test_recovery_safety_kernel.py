"""
P2.2 — Pure safety kernel tests (phone, canonical action, policy).
"""
import unittest
from datetime import datetime, timezone, time
from decimal import Decimal
import unicodedata

from services.payment_recovery.phone import normalize_indonesian_phone
from services.payment_recovery.actions import action_digest, canonical_scalar, build_canonical_action
from services.payment_recovery.policy import evaluate_policy, PolicyFact, parse_legacy_expiry


class PhoneNormalizationTests(unittest.TestCase):
    def test_valid_plus62(self):
        r = normalize_indonesian_phone("+628123456789")
        self.assertEqual(r.status, "valid")
        self.assertEqual(r.e164, "+628123456789")

    def test_valid_62(self):
        r = normalize_indonesian_phone("628123456789")
        self.assertEqual(r.status, "valid")
        self.assertEqual(r.e164, "+628123456789")

    def test_valid_08(self):
        r = normalize_indonesian_phone("08123456789")
        self.assertEqual(r.status, "valid")
        self.assertEqual(r.e164, "+628123456789")

    def test_valid_8(self):
        r = normalize_indonesian_phone("8123456789")
        self.assertEqual(r.status, "valid")
        self.assertEqual(r.e164, "+628123456789")

    def test_valid_with_separators(self):
        r = normalize_indonesian_phone("+62 812-3456-789 ( ) ")
        self.assertEqual(r.status, "valid")

    def test_invalid_too_short(self):
        r = normalize_indonesian_phone("08123")
        self.assertEqual(r.status, "invalid")

    def test_invalid_letters(self):
        r = normalize_indonesian_phone("0812abc789")
        self.assertEqual(r.status, "invalid")

    def test_unsupported_other_country(self):
        r = normalize_indonesian_phone("+12125551234")
        self.assertEqual(r.status, "unsupported")

    def test_empty_missing(self):
        r = normalize_indonesian_phone("")
        self.assertEqual(r.status, "invalid")
        self.assertEqual(r.reason, "recipient_missing")


class CanonicalActionTests(unittest.TestCase):
    def test_same_semantic_different_key_order_same_digest(self):
        action1 = {"b": 2, "a": 1, "amount": Decimal("175000.00")}
        action2 = {"a": 1, "b": 2, "amount": Decimal("175000.00")}
        self.assertEqual(action_digest(action1), action_digest(action2))

    def test_nfc_normalization(self):
        # NFD vs NFC should produce same canonical
        nfd = unicodedata.normalize("NFD", "é")
        nfc = unicodedata.normalize("NFC", "é")
        a1 = {"name": nfd}
        a2 = {"name": nfc}
        self.assertEqual(action_digest(a1), action_digest(a2))

    def test_decimal_canonical(self):
        a = {"amount": Decimal("175000.00")}
        canonical = canonical_scalar(a)
        self.assertEqual(canonical["amount"], "175000.00")

    def test_datetime_utc_z(self):
        dt = datetime(2026, 7, 13, 1, 0, 0, tzinfo=timezone.utc)
        canonical = canonical_scalar({"t": dt})
        self.assertEqual(canonical["t"], "2026-07-13T01:00:00Z")

    def test_naive_datetime_rejected(self):
        with self.assertRaises(ValueError):
            canonical_scalar({"t": datetime(2026, 7, 13, 1, 0, 0)})

    def test_single_bit_mutation_changes_digest(self):
        base = {
            "action_version": 1,
            "seller_id": 42,
            "amount": Decimal("175000.00"),
        }
        mutated = {
            "action_version": 1,
            "seller_id": 43,  # changed
            "amount": Decimal("175000.00"),
        }
        self.assertNotEqual(action_digest(base), action_digest(mutated))

    def test_golden_vector(self):
        # Fixed golden vector from blueprint example
        action = {
            "action_version": 1,
            "action_type": "payment_recovery",
            "purpose": "transactional_payment_reminder",
            "seller_id": 42,
            "opportunity_id": "4d152303-b6ae-44d2-b733-3cb1bea56b6c",
            "order_id": 991,
            "payment_attempt_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "amount": Decimal("175000.00"),
            "currency": "IDR",
            "payment_expires_at_utc": datetime(2026, 7, 13, 2, 0, 0, tzinfo=timezone.utc),
            "action_revision": 2,
            "contact_subject_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
            "contact_permission_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
            "recipient_fingerprint": "hmac-value",
            "channel_id": 77,
            "channel_type": "whatsapp",
            "provider_account_fingerprint": "hmac-value",
            "provider_template_name": "payment_reminder_v1",
            "provider_template_locale": "id",
            "provider_template_content_digest": "sha256",
            "provider_template_version": "v1",
            "template_params_digest": "sha256",
            "payment_reference_fingerprint": "hmac-value",
            "payment_reference_fingerprint_key_version": 3,
            "scheduled_at_utc": datetime(2026, 7, 13, 1, 0, 0, tzinfo=timezone.utc),
            "policy_version": 3,
        }
        digest = action_digest(action)
        # Should be 64-char hex
        self.assertEqual(len(digest), 64)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        # Same action should produce same digest
        self.assertEqual(digest, action_digest(action))


class PolicyEvaluationTests(unittest.TestCase):
    def _base_fact(self):
        return PolicyFact(
            seller_id=42,
            order_id=991,
            payment_attempt_id="attempt-1",
            amount=Decimal("175000.00"),
            currency="IDR",
            payment_expires_at=datetime(2026, 7, 13, 2, 0, 0, tzinfo=timezone.utc),
            payment_url_valid=True,
            consent_status="active",
            recipient_phone_normalized="+628123456789",
            recipient_phone_status="valid",
            quiet_hours_start=time(21, 0),
            quiet_hours_end=time(8, 0),
            recipient_timezone="Asia/Jakarta",
            current_time_utc=datetime(2026, 7, 12, 10, 0, 0, tzinfo=timezone.utc),
            mode="approval",
            paused=False,
            global_enabled=True,
            provider_template_approved=True,
            daily_cap_reached=False,
            cooldown_active=False,
            order_status="pending",
            attempt_is_current=True,
        )

    def test_eligible(self):
        fact = self._base_fact()
        decision = evaluate_policy(fact)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.suppression_code, None)

    def test_feature_disabled(self):
        fact = self._base_fact()
        fact = fact.__class__(**{**fact.__dict__, "global_enabled": False})
        decision = evaluate_policy(fact)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.suppression_code, "feature_disabled")

    def test_tenant_paused(self):
        fact = self._base_fact().__class__(**{**self._base_fact().__dict__, "paused": True})
        decision = evaluate_policy(fact)
        self.assertEqual(decision.suppression_code, "tenant_paused")

    def test_observe_only(self):
        fact = self._base_fact().__class__(**{**self._base_fact().__dict__, "mode": "observe"})
        decision = evaluate_policy(fact)
        self.assertEqual(decision.suppression_code, "observe_only")

    def test_order_not_pending(self):
        fact = self._base_fact().__class__(**{**self._base_fact().__dict__, "order_status": "paid"})
        decision = evaluate_policy(fact)
        self.assertEqual(decision.suppression_code, "order_not_pending")

    def test_payment_expired(self):
        fact = self._base_fact()
        expired = datetime(2026, 7, 10, 2, 0, 0, tzinfo=timezone.utc)
        fact = fact.__class__(**{**fact.__dict__, "payment_expires_at": expired})
        decision = evaluate_policy(fact)
        self.assertEqual(decision.suppression_code, "payment_expired")

    def test_consent_missing(self):
        fact = self._base_fact().__class__(**{**self._base_fact().__dict__, "consent_status": "missing"})
        decision = evaluate_policy(fact)
        self.assertEqual(decision.suppression_code, "consent_missing")

    def test_recipient_invalid(self):
        fact = self._base_fact().__class__(**{**self._base_fact().__dict__, "recipient_phone_status": "invalid", "recipient_phone_normalized": None})
        decision = evaluate_policy(fact)
        self.assertEqual(decision.suppression_code, "recipient_invalid")

    def test_legacy_expiry_invalid_suppress(self):
        self.assertIsNone(parse_legacy_expiry(""))
        self.assertIsNone(parse_legacy_expiry("invalid-date"))
        self.assertIsNotNone(parse_legacy_expiry("2026-07-13T02:00:00Z"))


if __name__ == "__main__":
    unittest.main()

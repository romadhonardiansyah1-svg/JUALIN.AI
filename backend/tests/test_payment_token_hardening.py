"""Regression coverage for legacy payment-token hardening (H2 + business regression)."""
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request


def _request(path="/api/payments/public/status/7"):
    return Request({
        "type": "http", "method": "GET", "path": path,
        "headers": [(b"x-real-ip", b"203.0.113.9")],
        "client": ("203.0.113.9", 1234),
    })


_NOW = object()  # distinguishes "default to now" from an explicit None created_at


def _order(
    *,
    token="valid-token",
    created_at=_NOW,
    expires_at=None,
    status="pending",
    paid_at=None,
):
    # A real Order.status is an OrderStatus member (has .value); the plain-string
    # cases below stand in for it. Pass an enum member through untouched so tests
    # can exercise the actual model enum without double-wrapping it.
    status_attr = status if hasattr(status, "value") else SimpleNamespace(value=status)
    return SimpleNamespace(
        id=7, seller_id=1, total=100000,
        payment_access_token=token,
        payment_access_token_expires_at=expires_at,
        created_at=datetime.now(timezone.utc) if created_at is _NOW else created_at,
        payment_provider=None, payment_method=None, payment_invoice_id=None,
        payment_url=None, payment_qr_data=None, payment_va_number=None,
        payment_expires_at=None, paid_at=paid_at,
        status=status_attr,
    )


class LegacyTokenExpiryTests(unittest.TestCase):
    """Expiry is bound to order STATUS, not age alone.

    An earlier revision of this suite asserted that ANY order older than 48h was
    rejected. That assertion was wrong as a business rule, not merely
    inconvenient: orders minted by ai.tools stay PENDING and genuinely payable
    long past 48h (auto-cancel needs 48h AND followup_count>=3, and its
    scheduler ships disabled), and there is no self-service token rotation
    because ENABLE_AI_ACTIONS defaults to false. So the old assertion pinned the
    behaviour "403 a customer who is still allowed to pay, with no recovery
    short of a manual DB edit". Age-based rejection is asserted below only where
    the token is genuinely useless: terminal orders, and the hard ceiling.
    """

    def test_pending_order_three_days_old_can_still_pay(self):
        from api.routes_payments import _verify_public_token

        order = _order(created_at=datetime.now(timezone.utc) - timedelta(days=3))
        _verify_public_token(order, "valid-token")

    def test_pending_order_survives_a_short_stamped_expiry(self):
        """A capability-length stamped TTL must not shorten a payable order."""
        from api.routes_payments import _verify_public_token

        now = datetime.now(timezone.utc)
        order = _order(
            created_at=now - timedelta(days=3),
            expires_at=now - timedelta(days=2),
        )
        _verify_public_token(order, "valid-token")

    def test_confirmed_order_is_still_payable(self):
        from api.routes_payments import _verify_public_token

        order = _order(
            created_at=datetime.now(timezone.utc) - timedelta(days=5),
            status="confirmed",
        )
        _verify_public_token(order, "valid-token")

    def test_pending_order_past_the_hard_ceiling_is_rejected(self):
        """Not an immortal token: the payable window still has a ceiling."""
        from api.routes_payments import (
            LEGACY_PAYMENT_LINK_TTL_DAYS,
            _verify_public_token,
        )

        order = _order(
            created_at=datetime.now(timezone.utc)
            - timedelta(days=LEGACY_PAYMENT_LINK_TTL_DAYS + 1)
        )
        with self.assertRaises(HTTPException) as raised:
            _verify_public_token(order, "valid-token")

        self.assertEqual(raised.exception.status_code, 403)

    def test_paid_order_with_old_token_is_rejected(self):
        from api.routes_payments import _verify_public_token

        now = datetime.now(timezone.utc)
        order = _order(
            created_at=now - timedelta(days=10),
            status="paid",
            paid_at=now - timedelta(days=9),
        )
        with self.assertRaises(HTTPException) as raised:
            _verify_public_token(order, "valid-token")

        self.assertEqual(raised.exception.status_code, 403)

    def test_cancelled_order_with_old_token_is_rejected(self):
        from api.routes_payments import _verify_public_token

        order = _order(
            created_at=datetime.now(timezone.utc) - timedelta(days=10),
            status="cancelled",
        )
        with self.assertRaises(HTTPException):
            _verify_public_token(order, "valid-token")

    def test_just_paid_order_still_opens_its_own_receipt(self):
        """Paying on day 3 must not 403 the buyer on the success page."""
        from api.routes_payments import _verify_public_token

        now = datetime.now(timezone.utc)
        order = _order(created_at=now - timedelta(days=3), status="paid", paid_at=now)
        _verify_public_token(order, "valid-token")

    def test_fresh_token_is_accepted(self):
        from api.routes_payments import _verify_public_token

        _verify_public_token(_order(), "valid-token")

    def test_naive_timestamps_are_treated_as_utc(self):
        from api.routes_payments import _verify_public_token

        order = _order(
            created_at=datetime.utcnow() - timedelta(days=10),
            status="cancelled",
        )
        with self.assertRaises(HTTPException):
            _verify_public_token(order, "valid-token")

    def test_legacy_ttl_is_not_the_capability_setting(self):
        """Two different lifetimes must not share one number."""
        import api.routes_payments as routes

        self.assertNotEqual(
            routes.LEGACY_PAYMENT_LINK_TTL_DAYS * 24,
            routes.settings.PAYMENT_CAPABILITY_TOKEN_TTL_HOURS,
        )


class LegacyTokenRealEnumTests(unittest.TestCase):
    """Bind the rule to the real OrderStatus enum, not to guessed strings.

    Every other test here fakes status as SimpleNamespace(value=...). These
    assert against models.order.OrderStatus so a renamed/removed member breaks
    the suite instead of silently making an order non-payable.
    """

    def test_payable_set_matches_the_real_enum_members(self):
        from api.routes_payments import _PAYABLE_STATUS_VALUES
        from models.order import OrderStatus

        self.assertEqual(
            _PAYABLE_STATUS_VALUES,
            frozenset({OrderStatus.PENDING.value, OrderStatus.CONFIRMED.value}),
        )

    def test_real_enum_instance_is_read_not_stringified(self):
        """order.status is a real SAEnum member at runtime, not a fake."""
        from api.routes_payments import _order_is_payable, _order_status_value
        from models.order import OrderStatus

        order = _order(status=OrderStatus.PENDING)
        self.assertEqual(_order_status_value(order), "pending")
        self.assertTrue(_order_is_payable(order))

    def test_every_payable_member_survives_an_old_order(self):
        from api.routes_payments import _PAYABLE_STATUS_VALUES, _verify_public_token
        from models.order import OrderStatus

        old = datetime.now(timezone.utc) - timedelta(days=7)
        for status in OrderStatus:
            if status.value not in _PAYABLE_STATUS_VALUES:
                continue
            with self.subTest(status=status.value):
                _verify_public_token(_order(created_at=old, status=status), "valid-token")

    def test_every_non_payable_member_enforces_expiry(self):
        from api.routes_payments import _PAYABLE_STATUS_VALUES, _verify_public_token
        from models.order import OrderStatus

        old = datetime.now(timezone.utc) - timedelta(days=7)
        for status in OrderStatus:
            if status.value in _PAYABLE_STATUS_VALUES:
                continue
            with self.subTest(status=status.value):
                with self.assertRaises(HTTPException) as raised:
                    _verify_public_token(_order(created_at=old, status=status), "valid-token")
                self.assertEqual(raised.exception.status_code, 403)

    def test_unknown_status_value_is_not_treated_as_payable(self):
        """Fail closed: a status this module has never heard of is not payable."""
        from api.routes_payments import _order_is_payable

        self.assertFalse(_order_is_payable(_order(status="some_future_status")))


class LegacyTokenMissingStampTests(unittest.TestCase):
    """Rows written before payment_access_token_expires_at existed.

    The migration adds the column nullable, and ai.actions only stamps it when
    ENABLE_AI_ACTIONS is on (default off). A NULL stamp must therefore never be
    read as "expired" on an order that is still payable.
    """

    def test_pending_order_with_null_stamp_is_accepted(self):
        from api.routes_payments import _verify_public_token

        order = _order(
            created_at=datetime.now(timezone.utc) - timedelta(days=10),
            expires_at=None,
        )
        _verify_public_token(order, "valid-token")

    def test_pending_order_without_created_at_is_accepted(self):
        """server_default means created_at is set, but a detached row may not be."""
        from api.routes_payments import _verify_public_token

        _verify_public_token(_order(created_at=None, expires_at=None), "valid-token")

    def test_terminal_order_without_any_timestamp_is_not_locked_open(self):
        """No anchor to expire from is the one case a terminal token survives."""
        from api.routes_payments import _legacy_token_hard_deadline

        order = _order(created_at=None, expires_at=None, status="cancelled")
        self.assertIsNone(_legacy_token_hard_deadline(order))


class AiOrderTokenStampTests(unittest.TestCase):
    def test_minted_link_expiry_matches_the_declared_ttl(self):
        from api.routes_payments import (
            LEGACY_PAYMENT_LINK_TTL_DAYS,
            legacy_payment_link_expiry,
        )

        now = datetime.now(timezone.utc)
        expiry = legacy_payment_link_expiry()
        self.assertGreater(expiry, now + timedelta(days=LEGACY_PAYMENT_LINK_TTL_DAYS - 1))
        self.assertLess(expiry, now + timedelta(days=LEGACY_PAYMENT_LINK_TTL_DAYS + 1))

    def test_tool_buat_order_stamps_the_expiry_column(self):
        import ai.tools

        source = Path(ai.tools.__file__).read_text(encoding="utf-8")
        self.assertIn(
            "payment_access_token_expires_at=legacy_payment_link_expiry()", source,
        )


class LegacyTokenComparisonTests(unittest.TestCase):
    def test_wrong_token_is_rejected_with_constant_time_compare(self):
        from api.routes_payments import _verify_public_token

        with patch(
            "api.routes_payments.secrets.compare_digest", return_value=False,
        ) as compare:
            with self.assertRaises(HTTPException) as raised:
                _verify_public_token(_order(), "wrong-token")

        self.assertEqual(raised.exception.status_code, 403)
        compare.assert_called_once()

    def test_wrong_token_on_an_expired_order_is_still_constant_time(self):
        """Expiry must never short-circuit ahead of the compare."""
        from api.routes_payments import _verify_public_token

        order = _order(
            created_at=datetime.now(timezone.utc) - timedelta(days=90),
            status="cancelled",
        )
        with patch(
            "api.routes_payments.secrets.compare_digest", return_value=False,
        ) as compare:
            with self.assertRaises(HTTPException) as raised:
                _verify_public_token(order, "wrong-token")

        self.assertEqual(raised.exception.status_code, 403)
        compare.assert_called_once()

    def test_missing_token_is_rejected(self):
        from api.routes_payments import _verify_public_token

        with self.assertRaises(HTTPException):
            _verify_public_token(_order(), None)

    def test_order_without_token_cannot_be_unlocked_by_empty_token(self):
        from api.routes_payments import _verify_public_token

        with self.assertRaises(HTTPException):
            _verify_public_token(_order(token=None), "")


class LegacyTokenLeakTests(unittest.TestCase):
    def test_error_detail_never_contains_the_token(self):
        from api.routes_payments import _verify_public_token

        secret = "super-secret-token-value"
        for order, supplied in (
            (_order(token=secret), "wrong-token"),
            (
                _order(
                    token=secret,
                    created_at=datetime.now(timezone.utc) - timedelta(days=10),
                    status="cancelled",
                ),
                secret,
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                _verify_public_token(order, supplied)
            rendered = repr(raised.exception.detail)
            self.assertNotIn(secret, rendered)
            self.assertNotIn("wrong-token", rendered)

    def test_expiry_log_record_never_contains_the_token(self):
        from api.routes_payments import _verify_public_token

        secret = "super-secret-token-value"
        order = _order(
            token=secret,
            created_at=datetime.now(timezone.utc) - timedelta(days=10),
            status="cancelled",
        )
        with patch("api.routes_payments.logger") as logger:
            with self.assertRaises(HTTPException):
                _verify_public_token(order, secret)

        self.assertTrue(logger.warning.called)
        self.assertNotIn(secret, repr(logger.warning.call_args))

    def test_wrong_token_and_expired_token_are_indistinguishable(self):
        from api.routes_payments import _verify_public_token

        with self.assertRaises(HTTPException) as wrong:
            _verify_public_token(_order(), "wrong-token")
        with self.assertRaises(HTTPException) as expired:
            _verify_public_token(
                _order(
                    created_at=datetime.now(timezone.utc) - timedelta(days=10),
                    status="cancelled",
                ),
                "valid-token",
            )

        self.assertEqual(wrong.exception.status_code, expired.exception.status_code)
        self.assertEqual(wrong.exception.detail, expired.exception.detail)


def _typed(status, allowed):
    from core.rate_limit import RateLimitResult

    return RateLimitResult(
        allowed=allowed, status=status, remaining=0, retry_after=60, limit=10,
    )


class LegacyPublicRateLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_rejects_when_rate_limit_exceeded(self):
        from api.routes_payments import get_public_payment_status

        db = AsyncMock()
        with patch(
            "core.rate_limit.check_rate_limit_typed",
            new=AsyncMock(return_value=_typed("denied", False)),
        ):
            with self.assertRaises(HTTPException) as raised:
                await get_public_payment_status(7, _request(), "valid-token", db)

        self.assertEqual(raised.exception.status_code, 429)
        db.execute.assert_not_awaited()

    async def test_methods_rejects_when_rate_limit_exceeded(self):
        from api.routes_payments import list_public_payment_methods

        db = AsyncMock()
        with patch(
            "core.rate_limit.check_rate_limit_typed",
            new=AsyncMock(return_value=_typed("denied", False)),
        ):
            with self.assertRaises(HTTPException) as raised:
                await list_public_payment_methods(7, _request(), "valid-token", db)

        self.assertEqual(raised.exception.status_code, 429)
        db.execute.assert_not_awaited()

    async def test_create_fails_closed_when_redis_unavailable(self):
        from api.routes_payments import PublicCreatePaymentRequest, create_public_payment

        db = AsyncMock()
        req = PublicCreatePaymentRequest(order_id=7, token="valid-token")
        with (
            patch(
                "core.rate_limit.check_rate_limit_typed",
                new=AsyncMock(return_value=_typed("dependency_unavailable", False)),
            ),
            patch(
                "services.payments.factory.create_payment_for_order", new=AsyncMock(),
            ) as create_payment,
        ):
            with self.assertRaises(HTTPException) as raised:
                await create_public_payment(_request("/api/payments/public/create"), req, db)

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(
            raised.exception.detail["error"], "security_dependency_unavailable",
        )
        db.execute.assert_not_awaited()
        create_payment.assert_not_awaited()

    async def test_create_rejects_when_rate_limit_exceeded_before_any_db_work(self):
        from api.routes_payments import PublicCreatePaymentRequest, create_public_payment

        db = AsyncMock()
        req = PublicCreatePaymentRequest(order_id=7, token="valid-token")
        with (
            patch(
                "core.rate_limit.check_rate_limit_typed",
                new=AsyncMock(return_value=_typed("denied", False)),
            ),
            patch(
                "services.payments.factory.create_payment_for_order", new=AsyncMock(),
            ) as create_payment,
        ):
            with self.assertRaises(HTTPException) as raised:
                await create_public_payment(_request("/api/payments/public/create"), req, db)

        self.assertEqual(raised.exception.status_code, 429)
        db.execute.assert_not_awaited()
        create_payment.assert_not_awaited()

    async def test_status_still_serves_when_rate_limit_allows(self):
        from api.routes_payments import get_public_payment_status

        query_result = MagicMock()
        query_result.scalar_one_or_none.return_value = _order()
        db = AsyncMock()
        db.execute.return_value = query_result

        with patch(
            "core.rate_limit.check_rate_limit_typed",
            new=AsyncMock(return_value=_typed("allowed", True)),
        ):
            payload = await get_public_payment_status(7, _request(), "valid-token", db)

        self.assertEqual(payload["order_id"], 7)
        self.assertNotIn("token", payload)


class AiPaymentLinkExpiryTests(unittest.TestCase):
    """_legacy_token_deadline is ADVISORY (rotation), not the enforcement rule."""

    def test_ai_minted_token_carries_an_expiry(self):
        from ai.actions import _legacy_token_expiry

        expiry = _legacy_token_expiry()
        self.assertGreater(expiry, datetime.now(timezone.utc))

    def test_stale_order_is_detected_for_token_rotation(self):
        from ai.actions import _legacy_token_is_stale

        stale = _order(created_at=datetime.now(timezone.utc) - timedelta(hours=48))
        self.assertTrue(_legacy_token_is_stale(stale))
        self.assertFalse(_legacy_token_is_stale(_order()))

    def test_rotation_advice_does_not_reject_a_payable_order(self):
        """Eager rotation is fine; eager rejection is the regression."""
        from ai.actions import _legacy_token_is_stale
        from api.routes_payments import _verify_public_token

        order = _order(created_at=datetime.now(timezone.utc) - timedelta(days=3))
        self.assertTrue(_legacy_token_is_stale(order))
        _verify_public_token(order, "valid-token")

    def test_stamped_link_is_not_rotated_while_it_still_works(self):
        """Rotation invalidates the URL already in the WhatsApp thread.

        An ai.tools-minted order carries the 30-day stamp, so a re-send during
        the payable window must hand back the SAME token the customer already
        has rather than silently breaking it.
        """
        from ai.actions import _legacy_token_is_stale
        from api.routes_payments import legacy_payment_link_expiry

        order = _order(
            created_at=datetime.now(timezone.utc) - timedelta(days=3),
            expires_at=legacy_payment_link_expiry(),
        )
        self.assertFalse(_legacy_token_is_stale(order))

    def test_rotation_advice_never_precedes_the_enforced_deadline(self):
        """Advisory deadline must not fire before the token actually dies."""
        from api.routes_payments import (
            _legacy_token_deadline,
            _legacy_token_hard_deadline,
            legacy_payment_link_expiry,
        )

        order = _order(
            created_at=datetime.now(timezone.utc) - timedelta(days=3),
            expires_at=legacy_payment_link_expiry(),
        )
        self.assertGreaterEqual(
            _legacy_token_deadline(order), _legacy_token_hard_deadline(order),
        )


if __name__ == "__main__":
    unittest.main()

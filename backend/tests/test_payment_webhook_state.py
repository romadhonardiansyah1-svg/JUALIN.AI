"""
P1.4 — Payment state monotonic and current-cycle matching (mocked).

Real DB concurrency requires disposable DB, but we test Decimal parsing
and monotonic state transitions with mocks.
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal


class PaymentWebhookMonotonicTests(unittest.IsolatedAsyncioTestCase):
    async def test_decimal_parsing_never_via_float(self):
        from services.payments.factory import _parse_decimal_amount

        # String amount should parse exactly
        self.assertEqual(_parse_decimal_amount("175000.00"), Decimal("175000.00"))
        self.assertEqual(_parse_decimal_amount("175000"), Decimal("175000"))
        # Comma removal: "175,000" -> 175000
        self.assertEqual(_parse_decimal_amount("175,000"), Decimal("175000"))
        # None returns None
        self.assertIsNone(_parse_decimal_amount(None))
        # Float passed as float should still parse via Decimal via str, not int(float)
        val = _parse_decimal_amount(175000.99)
        self.assertIsInstance(val, Decimal)
        # Ensure not truncated via int(float)
        self.assertNotEqual(val, Decimal("175000"))
        # Invalid string returns None
        self.assertIsNone(_parse_decimal_amount("not-a-number"))

    async def test_paid_does_not_downgrade_to_expired(self):
        from services.payments.factory import process_webhook
        from services.payments.base import PaymentStatus
        from models.order import Order, OrderStatus

        mock_db = AsyncMock()

        # Mock order already paid
        order = MagicMock(spec=Order)
        order.id = 1
        order.seller_id = 10
        order.status = OrderStatus.PAID
        order.total = 100000
        order.items = []
        order.paid_at = None

        mock_order_result = MagicMock()
        mock_order_result.scalar_one_or_none.return_value = order

        # Mock PaymentAttempt query returns None (no attempt table)
        mock_attempt_result = MagicMock()
        mock_attempt_result.scalar_one_or_none.return_value = None

        # Mock gateway validate returns expired status for same order
        mock_gateway = MagicMock()
        mock_gateway.validate_webhook = AsyncMock(
            return_value=MagicMock(
                valid=True,
                order_id="JUALIN-1",
                status=PaymentStatus.EXPIRED,
                amount=100000,
            )
        )

        with patch("services.payments.factory.get_payment_gateway", return_value=mock_gateway):
            # Mock db.execute side effects: first attempt lookup, then order lookup, then history check for stock restore
            mock_history_result = MagicMock()
            mock_history_result.scalars.return_value.first.return_value = None

            mock_db.execute.side_effect = [
                mock_attempt_result,  # PaymentAttempt lookup
                mock_order_result,  # Order lookup
                mock_history_result,  # history check for stock restore not needed because no restore
            ]

            with patch("core.audit.record_audit", new=AsyncMock()):
                result = await process_webhook(provider="midtrans", payload={}, headers={}, db=mock_db)

                self.assertTrue(result["success"])
                # Should stay paid, not downgrade to cancelled
                self.assertEqual(result["new_status"], "paid")

    async def test_refunded_does_not_return_to_paid(self):
        from services.payments.factory import process_webhook
        from services.payments.base import PaymentStatus
        from models.order import Order, OrderStatus

        mock_db = AsyncMock()
        order = MagicMock(spec=Order)
        order.id = 2
        order.seller_id = 10
        order.status = OrderStatus.REFUNDED
        order.total = 50000
        order.items = []

        mock_order_result = MagicMock()
        mock_order_result.scalar_one_or_none.return_value = order

        mock_attempt_result = MagicMock()
        mock_attempt_result.scalar_one_or_none.return_value = None

        mock_gateway = MagicMock()
        mock_gateway.validate_webhook = AsyncMock(
            return_value=MagicMock(valid=True, order_id="JUALIN-2", status=PaymentStatus.PAID, amount=50000)
        )

        with patch("services.payments.factory.get_payment_gateway", return_value=mock_gateway):
            mock_db.execute.side_effect = [
                mock_attempt_result,
                mock_order_result,
            ]
            with patch("core.audit.record_audit", new=AsyncMock()):
                result = await process_webhook(provider="cashi", payload={}, headers={}, db=mock_db)
                self.assertTrue(result["success"])
                # Should stay refunded
                self.assertEqual(result["new_status"], "refunded")

    async def test_get_status_read_only_no_provider_call(self):
        from api.routes_payments import get_payment_status
        from models.order import Order, OrderStatus

        mock_db = AsyncMock()
        order = MagicMock(spec=Order)
        order.id = 1
        order.seller_id = 10
        order.status = OrderStatus.PENDING
        order.payment_url = "https://pay.example/invoice"
        order.total = 100000

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = order
        mock_db.execute.return_value = mock_result

        current_user = MagicMock(id=10)

        # Patch _sync_payment_status to ensure it's NOT called (read-only)
        with patch("api.routes_payments._sync_payment_status", new=AsyncMock()) as mock_sync:
            result = await get_payment_status(order_id=1, current_user=current_user, db=mock_db)
            mock_sync.assert_not_awaited()
            self.assertEqual(result["order_id"], 1)

    async def test_amount_mismatch_rejected(self):
        from services.payments.factory import process_webhook
        from services.payments.base import PaymentStatus
        from models.order import Order, OrderStatus

        mock_db = AsyncMock()
        order = MagicMock(spec=Order)
        order.id = 3
        order.seller_id = 10
        order.status = OrderStatus.PENDING
        order.total = 100000
        order.items = []

        mock_order_result = MagicMock()
        mock_order_result.scalar_one_or_none.return_value = order

        # PaymentAttempt with amount 100000 but incoming 50000
        mock_attempt = MagicMock()
        mock_attempt.order_id = 3
        mock_attempt.seller_id = 10
        mock_attempt.amount = Decimal("100000.00")

        mock_attempt_result = MagicMock()
        mock_attempt_result.scalar_one_or_none.return_value = mock_attempt

        mock_gateway = MagicMock()
        mock_gateway.validate_webhook = AsyncMock(
            return_value=MagicMock(valid=True, order_id="JUALIN-3", status=PaymentStatus.PAID, amount=50000)
        )

        with patch("services.payments.factory.get_payment_gateway", return_value=mock_gateway):
            mock_db.execute.side_effect = [
                mock_attempt_result,
                mock_order_result,
            ]
            with patch("core.audit.record_audit", new=AsyncMock()):
                result = await process_webhook(provider="midtrans", payload={}, headers={}, db=mock_db)
                # Should fail due to amount mismatch when attempt present
                self.assertFalse(result["success"])
                self.assertIn("Amount mismatch", result["error"])

    async def test_paid_webhook_invokes_recovery_outcome_bridge(self):
        from services.payments.factory import process_webhook
        from services.payments.base import PaymentStatus
        from models.order import Order, OrderStatus

        mock_db = AsyncMock()
        order = MagicMock(spec=Order)
        order.id = 9
        order.seller_id = 10
        order.status = OrderStatus.PENDING
        order.total = 100000
        order.items = []
        order.paid_at = None

        mock_order_result = MagicMock()
        mock_order_result.scalar_one_or_none.return_value = order
        mock_attempt_result = MagicMock()
        mock_attempt_result.scalar_one_or_none.return_value = None
        mock_history_result = MagicMock()
        mock_history_result.scalars.return_value.first.return_value = None

        mock_gateway = MagicMock()
        mock_gateway.validate_webhook = AsyncMock(
            return_value=MagicMock(
                valid=True,
                order_id="JUALIN-9",
                status=PaymentStatus.PAID,
                amount=100000,
            )
        )
        outcome = {"applied": True, "reason": "recorded"}

        with patch("services.payments.factory.get_payment_gateway", return_value=mock_gateway):
            mock_db.execute.side_effect = [
                mock_attempt_result,
                mock_order_result,
            ]
            with (
                patch("core.audit.record_audit", new=AsyncMock()),
                patch(
                    "services.payment_recovery.outcomes.on_verified_payment",
                    new=AsyncMock(return_value=outcome),
                ) as bridge,
            ):
                result = await process_webhook(
                    provider="midtrans", payload={"gross_amount": "100000"}, headers={}, db=mock_db
                )

        self.assertTrue(result["success"])
        self.assertEqual(result["new_status"], "paid")
        self.assertEqual(result["recovery_outcome"], outcome)
        bridge.assert_awaited_once()
        kwargs = bridge.await_args.kwargs
        self.assertEqual(kwargs["seller_id"], 10)
        self.assertEqual(kwargs["order_id"], 9)
        self.assertEqual(kwargs["provider"], "midtrans")


if __name__ == "__main__":
    unittest.main()

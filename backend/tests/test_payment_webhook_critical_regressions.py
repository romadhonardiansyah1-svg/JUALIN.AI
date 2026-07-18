"""Critical payment webhook regression tests."""
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


class PaymentWebhookCriticalRegressionTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _order(order_id=3):
        from models.order import Order, OrderStatus

        order = MagicMock(spec=Order)
        order.id = order_id
        order.seller_id = 10
        order.status = OrderStatus.PENDING
        order.total = 100000
        order.items = []
        order.paid_at = None
        order.payment_invoice_id = None
        return order

    async def test_legacy_paid_amount_mismatch_is_rejected(self):
        from services.payments.base import PaymentStatus
        from services.payments.factory import process_webhook

        db = AsyncMock()
        no_attempt = MagicMock()
        no_attempt.scalar_one_or_none.return_value = None
        order_result = MagicMock()
        order_result.scalar_one_or_none.return_value = self._order()
        db.execute.side_effect = [no_attempt, order_result]

        gateway = MagicMock()
        gateway.validate_webhook = AsyncMock(return_value=MagicMock(
            valid=True, order_id="JUALIN-3", status=PaymentStatus.PAID, amount=50000,
        ))
        with patch("services.payments.factory.get_payment_gateway", return_value=gateway):
            result = await process_webhook("midtrans", {}, {}, db)

        self.assertFalse(result["success"])
        self.assertIn("Amount mismatch", result["error"])
        db.commit.assert_not_awaited()

    async def test_cashi_paid_amount_uses_verified_unique_suffix_attempt_amount(self):
        from services.payments.base import PaymentStatus
        from services.payments.factory import process_webhook

        attempt = SimpleNamespace(
            id="attempt-current", order_id=3, seller_id=10,
            amount=Decimal("100123"), is_current=True,
        )
        attempt_result = MagicMock()
        attempt_result.scalar_one_or_none.return_value = attempt
        order = self._order()
        order_result = MagicMock()
        order_result.scalar_one_or_none.return_value = order
        db = AsyncMock()
        db.add = MagicMock()
        db.execute.side_effect = [attempt_result, order_result]
        gateway = MagicMock()
        gateway.validate_webhook = AsyncMock(return_value=MagicMock(
            valid=True, order_id="JUALIN-3", status=PaymentStatus.PAID, amount=100123,
        ))

        with (
            patch("services.payments.factory.get_payment_gateway", return_value=gateway),
            patch("core.audit.record_audit", new=AsyncMock()),
            patch("services.payment_recovery.outcomes.on_verified_payment", new=AsyncMock(return_value={})),
        ):
            result = await process_webhook("cashi", {}, {}, db)

        self.assertTrue(result["success"])
        self.assertEqual(result["new_status"], "paid")

    async def test_cashi_webhook_uses_api_verified_amount_not_payload_amount(self):
        from services.payments.base import PaymentStatus
        from services.payments.cashi_gateway import CashiGateway

        gateway = object.__new__(CashiGateway)
        gateway.api_key = "test-key"
        gateway.check_status = AsyncMock(return_value=SimpleNamespace(
            status=PaymentStatus.PAID, amount=100123,
        ))

        result = await gateway.validate_webhook(
            {"order_id": "JUALIN-3", "status": "paid", "amount": 1},
            {"x-api-key": "test-key"},
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.amount, 100123)

    async def test_cashi_paid_webhook_without_verified_amount_is_rejected(self):
        from services.payments.base import PaymentStatus
        from services.payments.cashi_gateway import CashiGateway

        gateway = object.__new__(CashiGateway)
        gateway.api_key = "test-key"
        gateway.check_status = AsyncMock(return_value=SimpleNamespace(
            status=PaymentStatus.PAID, amount=None,
        ))

        result = await gateway.validate_webhook(
            {"order_id": "JUALIN-3", "status": "paid", "amount": 100000},
            {"x-api-key": "test-key"},
        )

        self.assertFalse(result.valid)
        self.assertIn("amount", result.error_message.lower())

    async def test_cashi_webhook_rejects_unverified_status_lookup(self):
        from services.payments.base import PaymentStatus
        from services.payments.cashi_gateway import CashiGateway

        gateway = object.__new__(CashiGateway)
        gateway.api_key = "test-key"
        gateway.check_status = AsyncMock(return_value=SimpleNamespace(
            status=PaymentStatus.PENDING, amount=None, verified=False,
        ))

        result = await gateway.validate_webhook(
            {"order_id": "JUALIN-3", "status": "paid", "amount": 100000},
            {"x-api-key": "test-key"},
        )

        self.assertFalse(result.valid)
        self.assertIn("verified", result.error_message.lower())

    async def test_stale_payment_attempt_is_rejected(self):
        from services.payments.base import PaymentStatus
        from services.payments.factory import process_webhook

        stale = MagicMock()
        stale.id = "attempt-old"
        stale.order_id = 3
        stale.seller_id = 10
        stale.amount = Decimal("100000")
        stale.is_current = False
        attempt_result = MagicMock()
        attempt_result.scalar_one_or_none.return_value = stale
        db = AsyncMock()
        db.execute.return_value = attempt_result

        gateway = MagicMock()
        gateway.validate_webhook = AsyncMock(return_value=MagicMock(
            valid=True, order_id="invoice-old", status=PaymentStatus.PAID, amount=100000,
        ))
        with patch("services.payments.factory.get_payment_gateway", return_value=gateway):
            result = await process_webhook("midtrans", {}, {}, db)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "stale payment attempt")
        self.assertEqual(db.execute.await_count, 1)

    async def test_order_is_row_locked_before_payment_state_transition(self):
        from services.payments.base import PaymentStatus
        from services.payments.factory import process_webhook

        no_attempt = MagicMock()
        no_attempt.scalar_one_or_none.return_value = None
        order_result = MagicMock()
        order_result.scalar_one_or_none.return_value = self._order(8)
        db = AsyncMock()
        db.execute.side_effect = [no_attempt, order_result]

        gateway = MagicMock()
        gateway.validate_webhook = AsyncMock(return_value=MagicMock(
            valid=True, order_id="JUALIN-8", status=PaymentStatus.FAILED, amount=100000,
        ))
        with patch("services.payments.factory.get_payment_gateway", return_value=gateway):
            result = await process_webhook("midtrans", {}, {}, db)

        self.assertTrue(result["success"])
        order_statement = str(db.execute.await_args_list[1].args[0]).upper()
        self.assertIn("FOR UPDATE", order_statement)

    async def test_paid_retry_does_not_move_processing_order_backward(self):
        from services.payments.base import PaymentStatus
        from services.payments.factory import process_webhook
        from models.order import OrderStatus

        order = self._order(11)
        order.status = OrderStatus.PROCESSING
        no_attempt = MagicMock()
        no_attempt.scalar_one_or_none.return_value = None
        order_result = MagicMock()
        order_result.scalar_one_or_none.return_value = order
        db = AsyncMock()
        db.execute.side_effect = [no_attempt, order_result]
        gateway = MagicMock()
        gateway.validate_webhook = AsyncMock(return_value=MagicMock(
            valid=True, order_id="JUALIN-11", status=PaymentStatus.PAID, amount=100000,
        ))

        with patch("services.payments.factory.get_payment_gateway", return_value=gateway):
            result = await process_webhook("midtrans", {}, {}, db)

        self.assertEqual(result["new_status"], "processing")
        self.assertEqual(order.status, OrderStatus.PROCESSING)

    async def test_paid_after_expiry_reconsumes_previously_restored_stock(self):
        from services.payments.base import PaymentStatus
        from services.payments.factory import process_webhook
        from models.order import OrderStatus

        order = self._order(12)
        order.status = OrderStatus.CANCELLED
        order.items = [{"product_id": 3, "qty": 2}]
        product = MagicMock()
        product.stok = 2
        no_attempt = MagicMock()
        no_attempt.scalar_one_or_none.return_value = None
        order_result = MagicMock()
        order_result.scalar_one_or_none.return_value = order
        product_result = MagicMock()
        product_result.scalar_one_or_none.return_value = product
        db = AsyncMock()
        db.add = MagicMock()
        db.execute.side_effect = [no_attempt, order_result, product_result]
        gateway = MagicMock()
        gateway.validate_webhook = AsyncMock(return_value=MagicMock(
            valid=True, order_id="JUALIN-12", status=PaymentStatus.PAID, amount=100000,
        ))

        with (
            patch("services.payments.factory.get_payment_gateway", return_value=gateway),
            patch("core.audit.record_audit", new=AsyncMock()),
            patch("services.payment_recovery.outcomes.on_verified_payment", new=AsyncMock(return_value={})),
        ):
            result = await process_webhook("midtrans", {}, {}, db)

        self.assertEqual(result["new_status"], "paid")
        self.assertEqual(product.stok, 0)


    async def test_refund_after_cancel_then_late_paid_restores_stock_again(self):
        from services.payments.base import PaymentStatus
        from services.payments.factory import process_webhook
        from models.order import OrderStatus

        order = self._order(13)
        order.status = OrderStatus.PAID
        order.items = [{"product_id": 3, "qty": 2}]
        product = MagicMock()
        product.stok = 0
        no_attempt = MagicMock()
        no_attempt.scalar_one_or_none.return_value = None
        order_result = MagicMock()
        order_result.scalar_one_or_none.return_value = order
        old_cancellation_history = MagicMock()
        old_cancellation_history.scalar_one_or_none.return_value = None
        product_result = MagicMock()
        product_result.scalar_one_or_none.return_value = product
        db = AsyncMock()
        db.add = MagicMock()
        calls = 0

        async def execute(statement):
            nonlocal calls
            calls += 1
            if calls == 1:
                return no_attempt
            if calls == 2:
                return order_result
            if "order_status_histories" in str(statement).lower():
                return old_cancellation_history
            return product_result

        db.execute.side_effect = execute
        gateway = MagicMock()
        gateway.validate_webhook = AsyncMock(return_value=MagicMock(
            valid=True, order_id="JUALIN-13", status=PaymentStatus.REFUNDED, amount=100000,
        ))

        with (
            patch("services.payments.factory.get_payment_gateway", return_value=gateway),
            patch("core.audit.record_audit", new=AsyncMock()),
            patch("services.payment_recovery.outcomes.record_payment_reversal", new=AsyncMock(return_value={})),
        ):
            result = await process_webhook("midtrans", {}, {}, db)

        self.assertEqual(result["new_status"], "refunded")
        self.assertEqual(product.stok, 2)

    async def test_late_paid_shortage_never_drives_stock_negative(self):
        from services.payments.base import PaymentStatus
        from services.payments.factory import process_webhook
        from models.order import OrderStatus

        order = self._order(16)
        order.status = OrderStatus.CANCELLED
        order.notes = ""
        order.items = [{"product_id": 3, "qty": 2}]
        product = SimpleNamespace(id=3, stok=1)
        no_attempt = MagicMock(); no_attempt.scalar_one_or_none.return_value = None
        order_result = MagicMock(); order_result.scalar_one_or_none.return_value = order
        product_result = MagicMock(); product_result.scalar_one_or_none.return_value = product
        db = AsyncMock(); db.add = MagicMock()
        db.execute.side_effect = [no_attempt, order_result, product_result]
        gateway = MagicMock()
        gateway.validate_webhook = AsyncMock(return_value=MagicMock(
            valid=True, order_id="JUALIN-16", status=PaymentStatus.PAID, amount=100000,
        ))

        with (
            patch("services.payments.factory.get_payment_gateway", return_value=gateway),
            patch("core.audit.record_audit", new=AsyncMock()),
            patch("services.payment_recovery.outcomes.on_verified_payment", new=AsyncMock(return_value={})),
        ):
            result = await process_webhook("midtrans", {}, {}, db)

        self.assertEqual(result["new_status"], "paid")
        self.assertEqual(product.stok, 1)
        self.assertEqual(result["stock_shortage_product_ids"], [3])
        self.assertIn("stok tidak cukup", order.notes.lower())

    async def test_refund_after_seller_cancellation_records_reversal_without_double_restore(self):
        from services.payments.base import PaymentStatus
        from services.payments.factory import process_webhook
        from models.order import OrderStatus

        order = self._order(17)
        order.status = OrderStatus.CANCELLED
        order.notes = ""
        order.items = [{"product_id": 3, "qty": 2}]
        no_attempt = MagicMock(); no_attempt.scalar_one_or_none.return_value = None
        order_result = MagicMock(); order_result.scalar_one_or_none.return_value = order
        db = AsyncMock(); db.add = MagicMock()
        db.execute.side_effect = [no_attempt, order_result]
        gateway = MagicMock()
        gateway.validate_webhook = AsyncMock(return_value=MagicMock(
            valid=True, order_id="JUALIN-17", status=PaymentStatus.REFUNDED, amount=100000,
        ))
        reversal = AsyncMock(return_value={})

        with (
            patch("services.payments.factory.get_payment_gateway", return_value=gateway),
            patch("core.audit.record_audit", new=AsyncMock()),
            patch("services.payment_recovery.outcomes.record_payment_reversal", new=reversal),
        ):
            result = await process_webhook("midtrans", {}, {}, db)

        self.assertEqual(result["new_status"], "refunded")
        reversal.assert_awaited_once()
        self.assertEqual(db.execute.await_count, 2)

    async def test_refund_skips_stock_never_consumed_during_late_paid_shortage(self):
        from services.payments.base import PaymentStatus
        from services.payments.factory import process_webhook
        from models.order import OrderStatus

        order = self._order(18)
        order.status = OrderStatus.PAID
        order.notes = "seller may replace this note"
        order.items = [
            {"product_id": 3, "qty": 1},
            {"product_id": 3, "qty": 2},
        ]
        product = SimpleNamespace(id=3, stok=0)
        no_attempt = MagicMock(); no_attempt.scalar_one_or_none.return_value = None
        order_result = MagicMock(); order_result.scalar_one_or_none.return_value = order
        history_result = MagicMock()
        history_result.scalar_one_or_none.return_value = (
            "Payment paid via midtrans; late_paid_consumed=3:1;"
        )
        product_result = MagicMock(); product_result.scalar_one_or_none.return_value = product
        db = AsyncMock(); db.add = MagicMock()
        db.execute.side_effect = [no_attempt, order_result, history_result, product_result]
        gateway = MagicMock()
        gateway.validate_webhook = AsyncMock(return_value=MagicMock(
            valid=True, order_id="JUALIN-18", status=PaymentStatus.REFUNDED, amount=100000,
        ))

        with (
            patch("services.payments.factory.get_payment_gateway", return_value=gateway),
            patch("core.audit.record_audit", new=AsyncMock()),
            patch("services.payment_recovery.outcomes.record_payment_reversal", new=AsyncMock(return_value={})),
        ):
            result = await process_webhook("midtrans", {}, {}, db)

        self.assertEqual(result["new_status"], "refunded")
        self.assertEqual(product.stok, 1)
        self.assertEqual(db.execute.await_count, 4)

    async def test_midtrans_partial_refund_does_not_become_full_refund(self):
        from services.payments.base import PaymentStatus
        from services.payments.midtrans_gateway import MidtransGateway

        gateway = object.__new__(MidtransGateway)
        gateway.api_url = "https://api.example"
        gateway._auth_header = "auth"
        response = MagicMock()
        response.json.return_value = {
            "transaction_status": "partial_refund",
            "gross_amount": "100000.00",
        }
        client = AsyncMock(); client.get.return_value = response
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=None)

        with patch("services.payments.midtrans_gateway.httpx.AsyncClient", return_value=context):
            result = await gateway.check_status("JUALIN-19")

        self.assertEqual(result.status, PaymentStatus.PARTIALLY_REFUNDED)


if __name__ == "__main__":
    unittest.main()

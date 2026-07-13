"""
P0.2 — Fail-closed followup handler and tenant isolation.
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace


class FollowupJobSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Mock models
        self.mock_order = MagicMock()
        self.mock_order.id = 1
        self.mock_order.seller_id = 10
        self.mock_order.status = "pending"  # will be patched to enum
        self.mock_order.followup_count = 0
        self.mock_order.customer_name = "Test Customer"
        self.mock_order.customer_phone = "+6281234567890"
        self.mock_order.items = "Item A"
        self.mock_order.total = 100000

        # For status comparison, we need OrderStatus.PENDING enum
        from models.order import OrderStatus
        self.OrderStatus = OrderStatus
        self.mock_order.status = OrderStatus.PENDING

    async def test_provider_returns_false_not_marked_done(self):
        """Provider returns success=False should NOT mark followup sent and job not done."""
        from services.job_handlers import handle_pending_payment_followup
        from models.order import Order

        job = SimpleNamespace(
            payload={"order_id": 1},
            seller_id=10,
        )

        # Mock DB that returns order with matching seller_id
        mock_db = AsyncMock()
        # First execute: select Order where id==order_id
        # We'll mock execute to return order
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = self.mock_order
        mock_db.execute.return_value = mock_result

        # Mock channel lookup to return channel
        # Second execute for channel
        # We need side_effect for two calls: order, then channel
        mock_channel = MagicMock()
        mock_channel.seller_id = 10
        mock_channel.type = "whatsapp"
        mock_channel.status = "active"
        mock_channel.external_id = "phone-id"
        mock_channel.config_encrypted = ""

        mock_channel_result = MagicMock()
        mock_channel_result.scalar_one_or_none.return_value = mock_channel

        # For order and channel, return in sequence
        mock_db.execute.side_effect = [mock_result, mock_channel_result]

        # Mock decrypt and provider to return failure
        with patch("services.job_handlers.decrypt_config", return_value={"access_token": "tok", "phone_number_id": "id"}):
            mock_provider_instance = MagicMock()
            mock_provider_instance.send_message = AsyncMock(return_value=MagicMock(success=False, error_message="provider rejected"))
            with patch("services.job_handlers.WhatsAppCloudProvider", return_value=mock_provider_instance):
                with patch("ai.followup.mark_followup_sent", new=AsyncMock()) as mock_mark:
                    result = await handle_pending_payment_followup(mock_db, job)

                    # Should NOT be success True with sent_via log; should be failure
                    self.assertFalse(result.get("success"), f"Expected failure when provider rejected, got {result}")
                    mock_mark.assert_not_awaited()

    async def test_provider_raises_no_mark(self):
        from services.job_handlers import handle_pending_payment_followup

        job = SimpleNamespace(payload={"order_id": 1}, seller_id=10)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = self.mock_order
        mock_db.execute.return_value = mock_result

        mock_channel = MagicMock()
        mock_channel.seller_id = 10
        mock_channel.config_encrypted = ""
        mock_channel_result = MagicMock()
        mock_channel_result.scalar_one_or_none.return_value = mock_channel
        mock_db.execute.side_effect = [mock_result, mock_channel_result]

        with patch("services.job_handlers.decrypt_config", return_value={"access_token": "tok", "phone_number_id": "id"}):
            mock_provider_instance = MagicMock()
            mock_provider_instance.send_message = AsyncMock(side_effect=Exception("network timeout"))
            with patch("services.job_handlers.WhatsAppCloudProvider", return_value=mock_provider_instance):
                with patch("ai.followup.mark_followup_sent", new=AsyncMock()) as mock_mark:
                    result = await handle_pending_payment_followup(mock_db, job)
                    self.assertFalse(result.get("success"))
                    mock_mark.assert_not_awaited()

    async def test_log_mode_never_considered_success(self):
        """sent_via=log must not be treated as outbound success and must not mark sent."""
        from services.job_handlers import handle_pending_payment_followup

        job = SimpleNamespace(payload={"order_id": 1}, seller_id=10)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = self.mock_order
        # No channel found
        mock_channel_result = MagicMock()
        mock_channel_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [mock_result, mock_channel_result]

        with patch("ai.followup.mark_followup_sent", new=AsyncMock()) as mock_mark:
            result = await handle_pending_payment_followup(mock_db, job)
            # Should be failure / not success with log
            self.assertFalse(result.get("success") and result.get("sent_via") == "log",
                             "log mode should never be considered success")
            # If it returns success, sent_via must not be log
            if result.get("success"):
                self.assertNotEqual(result.get("sent_via"), "log")
            mock_mark.assert_not_awaited()

    async def test_cross_tenant_order_is_rejected(self):
        """Job seller A + order seller B => suppressed/security outcome, zero mutation/provider call."""
        from services.job_handlers import handle_pending_payment_followup

        job = SimpleNamespace(payload={"order_id": 1}, seller_id=999)  # attacker seller_id different

        # Order belongs to seller 10, not 999
        mock_order = MagicMock()
        mock_order.id = 1
        mock_order.seller_id = 10
        from models.order import OrderStatus
        mock_order.status = OrderStatus.PENDING

        mock_db = AsyncMock()
        # Here we test tenant-scoped lookup: if handler uses Order.id AND seller_id, it should return None
        # Simulate that lookup returns None for mismatched tenant
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # tenant mismatch -> not found
        mock_db.execute.return_value = mock_result

        with patch("ai.followup.mark_followup_sent", new=AsyncMock()) as mock_mark:
            with patch("services.job_handlers.WhatsAppCloudProvider") as mock_provider_cls:
                result = await handle_pending_payment_followup(mock_db, job)
                self.assertFalse(result.get("success") and result.get("sent_via") == "whatsapp",
                                 "Cross-tenant should not succeed")
                # Should be suppressed / not found, not success
                # Ensure mark not called and provider not instantiated
                mock_mark.assert_not_awaited()
                mock_provider_cls.assert_not_called()

    async def test_missing_order_typed_terminal(self):
        from services.job_handlers import handle_pending_payment_followup

        job = SimpleNamespace(payload={"order_id": 9999}, seller_id=10)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await handle_pending_payment_followup(mock_db, job)
        self.assertFalse(result.get("success"))
        self.assertIn("order not found", result.get("error", "").lower() or result.get("reason", "").lower() or str(result).lower())

    async def test_missing_order_id(self):
        from services.job_handlers import handle_pending_payment_followup

        job = SimpleNamespace(payload={}, seller_id=10)
        mock_db = AsyncMock()
        result = await handle_pending_payment_followup(mock_db, job)
        self.assertFalse(result.get("success"))
        self.assertIn("order_id", result.get("error", "").lower())

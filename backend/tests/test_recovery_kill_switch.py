"""P4.6 — Recovery kill switch fail-closed revalidation."""
from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from services.payment_recovery.dispatch import revalidate_before_send


def _scalar(value):
    m = MagicMock()
    m.scalar_one_or_none.return_value = value
    return m


class KillSwitchRevalidationTests(unittest.IsolatedAsyncioTestCase):
    async def _base_ok_entities(self):
        dispatch = SimpleNamespace(
            opportunity_id=uuid.uuid4(),
            approval_id=1,
            contact_permission_id=uuid.uuid4(),
            seller_id=10,
        )
        opportunity = SimpleNamespace(
            seller_id=10,
            status="dispatch_pending",
            order_id=5,
            payment_attempt_id=uuid.uuid4(),
        )
        approval = SimpleNamespace(seller_id=10, status="approved")
        order = SimpleNamespace(seller_id=10, status=SimpleNamespace(value="pending"), paid_at=None)
        # OrderStatus.PENDING comparison — use real enum
        from models.order import OrderStatus

        order.status = OrderStatus.PENDING
        attempt = SimpleNamespace(is_current=True, payment_expires_at=None)
        permission = SimpleNamespace(contact_subject_id=uuid.uuid4())
        return dispatch, opportunity, approval, order, attempt, permission

    async def test_global_paused_blocks_send(self):
        (
            dispatch,
            opportunity,
            approval,
            order,
            attempt,
            permission,
        ) = await self._base_ok_entities()
        control = SimpleNamespace(enabled=True, paused=True)
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar(dispatch),
                _scalar(opportunity),
                _scalar(approval),
                _scalar(order),
                _scalar(attempt),
                _scalar(permission),
                _scalar(None),  # suppression
                _scalar(control),
            ]
        )
        with patch(
            "config.get_settings",
            return_value=SimpleNamespace(ENABLE_PAYMENT_RECOVERY=True),
        ):
            allowed, reason = await revalidate_before_send(
                db, seller_id=10, dispatch_id=dispatch.opportunity_id
            )
        self.assertFalse(allowed)
        self.assertEqual(reason, "global_paused")

    async def test_tenant_paused_blocks_send(self):
        (
            dispatch,
            opportunity,
            approval,
            order,
            attempt,
            permission,
        ) = await self._base_ok_entities()
        control = SimpleNamespace(enabled=True, paused=False)
        policy = SimpleNamespace(payment_recovery_paused=True)
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar(dispatch),
                _scalar(opportunity),
                _scalar(approval),
                _scalar(order),
                _scalar(attempt),
                _scalar(permission),
                _scalar(None),
                _scalar(control),
                _scalar(policy),
            ]
        )
        with patch(
            "config.get_settings",
            return_value=SimpleNamespace(ENABLE_PAYMENT_RECOVERY=True),
        ):
            allowed, reason = await revalidate_before_send(
                db, seller_id=10, dispatch_id=uuid.uuid4()
            )
        self.assertFalse(allowed)
        self.assertEqual(reason, "tenant_paused")

    def test_runbook_exists_without_secrets(self):
        from pathlib import Path

        path = Path(__file__).resolve().parents[2] / "docs" / "recovery-kill-switch-runbook.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("PUT /api/system/recovery-control", text)
        self.assertNotIn("eyJ", text)
        self.assertNotIn("Bearer ", text)


if __name__ == "__main__":
    unittest.main()

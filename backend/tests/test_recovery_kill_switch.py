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
        from decimal import Decimal

        from models.order import OrderStatus
        from services.payment_recovery.actions import action_digest
        from services.payment_recovery.approval_materializer import (
            build_bound_recovery_action,
        )

        opportunity = SimpleNamespace(
            id=uuid.uuid4(),
            seller_id=10,
            status="dispatch_pending",
            order_id=5,
            payment_attempt_id=uuid.uuid4(),
            amount_snapshot=Decimal("10000.00"),
            currency="IDR",
        )
        order = SimpleNamespace(
            id=opportunity.order_id,
            seller_id=10,
            status=OrderStatus.PENDING,
            paid_at=None,
        )
        attempt = SimpleNamespace(
            id=opportunity.payment_attempt_id,
            seller_id=10,
            order_id=order.id,
            amount=Decimal("10000.00"),
            is_current=True,
            payment_expires_at=None,
            trusted_link_reference="payment-reference",
            external_attempt_id="attempt-1",
        )
        permission = SimpleNamespace(
            id=uuid.uuid4(),
            seller_id=10,
            order_id=order.id,
            payment_attempt_id=attempt.id,
            contact_subject_id=uuid.uuid4(),
            address_fingerprint="recipient-fingerprint",
            channel="whatsapp",
            purpose="transactional_payment_reminder",
            scope_type="order_payment_cycle",
            status="active",
            expires_at=None,
        )
        channel = SimpleNamespace(
            id=7,
            seller_id=10,
            type="whatsapp",
            provider="whatsapp_cloud",
            status="active",
            external_id="phone-number-id",
        )
        template = SimpleNamespace(
            id=8,
            seller_id=10,
            name="payment_reminder_v1",
            language="id",
            body="Bayar {{1}} {{2}}",
            variables_json=[{"key": "order"}, {"key": "amount"}],
            provider_template_id="provider-template-8",
            status="approved",
        )
        action, template_params = build_bound_recovery_action(
            opportunity=opportunity,
            order=order,
            attempt=attempt,
            permission=permission,
            channel=channel,
            template=template,
            scheduled_at="2026-07-17T07:00:00Z",
            policy_version=1,
        )
        digest = action_digest(action)
        dispatch = SimpleNamespace(
            opportunity_id=opportunity.id,
            approval_id=1,
            action_digest=digest,
            contact_permission_id=permission.id,
            contact_subject_id=permission.contact_subject_id,
            recipient_fingerprint=permission.address_fingerprint,
            seller_id=10,
            channel_id=channel.id,
            channel_type=channel.type,
            provider=channel.provider,
            template_code=template.name,
            template_params_json=template_params,
        )
        approval = SimpleNamespace(
            seller_id=10,
            status="approved",
            action_digest=digest,
            policy_version=1,
            detail_json={"template_id": template.id, "action": action},
        )
        return dispatch, opportunity, approval, order, attempt, permission, channel, template

    async def test_global_paused_blocks_send(self):
        (
            dispatch,
            opportunity,
            approval,
            order,
            attempt,
            permission,
            channel,
            template,
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
                _scalar(channel),
                _scalar(template),
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
            channel,
            template,
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
                _scalar(channel),
                _scalar(template),
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

    async def test_provider_account_change_invalidates_approved_action(self):
        (
            dispatch,
            opportunity,
            approval,
            order,
            attempt,
            permission,
            channel,
            _template,
        ) = await self._base_ok_entities()
        channel.external_id = "different-phone-number-id"
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar(dispatch),
                _scalar(opportunity),
                _scalar(approval),
                _scalar(order),
                _scalar(attempt),
                _scalar(permission),
                _scalar(channel),
                _scalar(_template),
            ]
        )

        allowed, reason = await revalidate_before_send(
            db, seller_id=10, dispatch_id=dispatch.opportunity_id
        )

        self.assertFalse(allowed)
        self.assertEqual(reason, "approval_stale")

    async def test_template_change_invalidates_approved_action(self):
        (
            dispatch,
            opportunity,
            approval,
            order,
            attempt,
            permission,
            channel,
            template,
        ) = await self._base_ok_entities()
        template.provider_template_id = "replacement-template"
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar(dispatch),
                _scalar(opportunity),
                _scalar(approval),
                _scalar(order),
                _scalar(attempt),
                _scalar(permission),
                _scalar(channel),
                _scalar(template),
            ]
        )

        allowed, reason = await revalidate_before_send(
            db, seller_id=10, dispatch_id=dispatch.opportunity_id
        )

        self.assertFalse(allowed)
        self.assertEqual(reason, "approval_stale")

    async def test_payment_amount_change_invalidates_approved_action(self):
        (
            dispatch,
            opportunity,
            approval,
            order,
            attempt,
            permission,
            channel,
            template,
        ) = await self._base_ok_entities()
        attempt.amount = attempt.amount * 2
        opportunity.amount_snapshot = attempt.amount
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalar(dispatch),
                _scalar(opportunity),
                _scalar(approval),
                _scalar(order),
                _scalar(attempt),
                _scalar(permission),
                _scalar(channel),
                _scalar(template),
            ]
        )

        allowed, reason = await revalidate_before_send(
            db, seller_id=10, dispatch_id=dispatch.opportunity_id
        )

        self.assertFalse(allowed)
        self.assertEqual(reason, "approval_stale")

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

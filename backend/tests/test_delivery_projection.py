"""
P4.2a — Project durable delivery facts onto recovery domain.
"""
from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from services.payment_recovery.delivery_projection import (
    delivery_rank,
    project_whatsapp_delivery_fact,
    should_advance_delivery,
)

_UNSET = object()


def _result(scalar):
    m = MagicMock()
    m.scalar_one_or_none.return_value = scalar
    return m


class DeliveryRankTests(unittest.TestCase):
    def test_monotonic_positive_ranks(self):
        self.assertLess(delivery_rank("sent"), delivery_rank("delivered"))
        self.assertLess(delivery_rank("delivered"), delivery_rank("read"))
        self.assertTrue(should_advance_delivery("sent", "delivered"))
        self.assertTrue(should_advance_delivery("delivered", "read"))
        self.assertFalse(should_advance_delivery("read", "delivered"))
        self.assertFalse(should_advance_delivery("read", "sent"))

    def test_failed_does_not_downgrade_delivered_or_read(self):
        self.assertFalse(should_advance_delivery("delivered", "failed"))
        self.assertFalse(should_advance_delivery("read", "failed"))
        self.assertTrue(should_advance_delivery("sent", "failed"))
        self.assertTrue(should_advance_delivery("not_available", "failed"))


class DeliveryProjectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.seller_id = 42
        self.channel_id = 7
        self.opportunity_id = uuid.uuid4()
        self.dispatch_id = uuid.uuid4()
        self.channel = SimpleNamespace(
            id=self.channel_id,
            seller_id=self.seller_id,
            external_id="phone-number-1",
            provider="whatsapp_cloud",
            type="whatsapp",
            status="active",
        )
        self.dispatch = SimpleNamespace(
            id=self.dispatch_id,
            seller_id=self.seller_id,
            opportunity_id=self.opportunity_id,
            provider="whatsapp_cloud",
            channel_id=self.channel_id,
            provider_message_id="wamid.abc",
            status="provider_unknown",
            delivery_status="not_available",
            accepted_at=None,
            delivered_at=None,
            read_at=None,
            delivery_failed_at=None,
        )
        self.opportunity = SimpleNamespace(
            id=self.opportunity_id,
            seller_id=self.seller_id,
            status="dispatch_pending",
            state_version=1,
        )

    async def _project(
        self,
        fact,
        *,
        channel=_UNSET,
        dispatch=_UNSET,
        opportunity=_UNSET,
    ):
        db = AsyncMock()
        channel_value = self.channel if channel is _UNSET else channel
        dispatch_value = self.dispatch if dispatch is _UNSET else dispatch
        side_effects = [_result(channel_value)]
        if channel_value is not None:
            side_effects.append(_result(dispatch_value))
        if (
            opportunity is not False
            and channel_value is not None
            and dispatch_value is not None
            and str(fact.get("status") or "").lower() in {"delivered", "read"}
            and getattr(dispatch_value, "status", None) in {"request_in_flight", "provider_unknown"}
        ):
            opp_value = self.opportunity if opportunity is _UNSET else opportunity
            side_effects.append(_result(opp_value))
        db.execute = AsyncMock(side_effect=side_effects)
        return await project_whatsapp_delivery_fact(db, fact=fact), db

    async def test_delivered_promotes_provider_unknown_to_accepted(self):
        result, _ = await self._project(
            {
                "provider": "whatsapp_cloud",
                "provider_account_id": "phone-number-1",
                "message_id": "wamid.abc",
                "status": "delivered",
                "timestamp": "1700000000",
            }
        )
        self.assertTrue(result["applied"])
        self.assertEqual(self.dispatch.status, "accepted")
        self.assertEqual(self.dispatch.delivery_status, "delivered")
        self.assertIsNotNone(self.dispatch.accepted_at)
        self.assertIsNotNone(self.dispatch.delivered_at)
        self.assertEqual(self.opportunity.status, "dispatched")
        self.assertEqual(self.opportunity.state_version, 2)
        self.assertIn("submission:provider_unknown->accepted", result["transitions"])
        self.assertIn("opportunity:dispatch_pending->dispatched", result["transitions"])

    async def test_read_before_delivered_is_monotonic(self):
        self.dispatch.status = "accepted"
        self.dispatch.accepted_at = self.dispatch.accepted_at
        self.dispatch.delivery_status = "not_available"
        result, db = await self._project(
            {
                "provider": "whatsapp_cloud",
                "provider_account_id": "phone-number-1",
                "message_id": "wamid.abc",
                "status": "read",
                "timestamp": "1700000001",
            },
            opportunity=False,
        )
        # accepted dispatch does not need opportunity load for promotion
        self.assertTrue(result["applied"])
        self.assertEqual(self.dispatch.delivery_status, "read")
        self.assertIsNotNone(self.dispatch.delivered_at)
        self.assertIsNotNone(self.dispatch.read_at)
        # No acceptance transition when already accepted
        self.assertTrue(all(not t.startswith("submission:") for t in result["transitions"]))
        self.assertEqual(db.execute.await_count, 2)

    async def test_failed_after_accepted_does_not_downgrade_or_resend(self):
        self.dispatch.status = "accepted"
        self.dispatch.delivery_status = "delivered"
        self.dispatch.delivered_at = object()
        result, _ = await self._project(
            {
                "provider": "whatsapp_cloud",
                "provider_account_id": "phone-number-1",
                "message_id": "wamid.abc",
                "status": "failed",
                "timestamp": "1700000002",
            },
            opportunity=False,
        )
        self.assertFalse(result["applied"])
        self.assertEqual(self.dispatch.status, "accepted")
        self.assertEqual(self.dispatch.delivery_status, "delivered")
        self.assertIsNone(self.dispatch.delivery_failed_at)

    async def test_failed_before_delivery_sets_delivery_only(self):
        self.dispatch.status = "accepted"
        self.dispatch.delivery_status = "sent"
        result, _ = await self._project(
            {
                "provider": "whatsapp_cloud",
                "provider_account_id": "phone-number-1",
                "message_id": "wamid.abc",
                "status": "failed",
                "timestamp": "1700000002",
            },
            opportunity=False,
        )
        self.assertTrue(result["applied"])
        self.assertEqual(self.dispatch.status, "accepted")
        self.assertEqual(self.dispatch.delivery_status, "failed")
        self.assertIsNotNone(self.dispatch.delivery_failed_at)

    async def test_duplicate_delivered_is_noop(self):
        self.dispatch.status = "accepted"
        self.dispatch.delivery_status = "delivered"
        self.dispatch.delivered_at = object()
        result, _ = await self._project(
            {
                "provider": "whatsapp_cloud",
                "provider_account_id": "phone-number-1",
                "message_id": "wamid.abc",
                "status": "delivered",
                "timestamp": "1700000000",
            },
            opportunity=False,
        )
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "no_transition")

    async def test_unknown_message_does_not_cross_tenant_guess(self):
        result, db = await self._project(
            {
                "provider": "whatsapp_cloud",
                "provider_account_id": "phone-number-1",
                "message_id": "wamid.unknown",
                "status": "delivered",
                "timestamp": "1700000000",
            },
            dispatch=None,
            opportunity=False,
        )
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "dispatch_not_found")
        self.assertEqual(result["seller_id"], self.seller_id)
        self.assertEqual(db.execute.await_count, 2)

    async def test_wrong_channel_account_is_not_mapped(self):
        result, _ = await self._project(
            {
                "provider": "whatsapp_cloud",
                "provider_account_id": "other-account",
                "message_id": "wamid.abc",
                "status": "delivered",
                "timestamp": "1700000000",
            },
            channel=None,
            opportunity=False,
        )
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "channel_not_found")

    async def test_request_in_flight_delivered_becomes_accepted(self):
        self.dispatch.status = "request_in_flight"
        result, _ = await self._project(
            {
                "provider": "whatsapp_cloud",
                "provider_account_id": "phone-number-1",
                "message_id": "wamid.abc",
                "status": "delivered",
                "timestamp": "1700000000",
            }
        )
        self.assertTrue(result["applied"])
        self.assertEqual(self.dispatch.status, "accepted")
        self.assertEqual(self.opportunity.status, "dispatched")

    async def test_invalid_fact_is_rejected(self):
        result, db = await self._project(
            {
                "provider": "whatsapp_cloud",
                "provider_account_id": "",
                "message_id": "wamid.abc",
                "status": "delivered",
            },
            opportunity=False,
        )
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "invalid_delivery_fact")
        db.execute.assert_not_awaited()

    def test_webhook_route_calls_projection_after_inbox(self):
        import inspect
        from api import routes_webhooks

        source = inspect.getsource(routes_webhooks.whatsapp_cloud_webhook)
        self.assertIn("project_whatsapp_delivery_fact", source)
        self.assertIn("get_or_create_webhook_event_composite", source)
        self.assertIn("provider_account_id", source)


if __name__ == "__main__":
    unittest.main()

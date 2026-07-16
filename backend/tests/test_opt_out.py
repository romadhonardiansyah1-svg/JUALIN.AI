"""
P4.3 — STOP / BERHENTI transactional opt-out.
"""
from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from services.payment_recovery.opt_out import (
    apply_transactional_stop,
    is_transactional_stop_keyword,
)


def _result(value, *, many=False):
    m = MagicMock()
    if many:
        m.scalars.return_value.all.return_value = value
        m.all.return_value = value
    else:
        m.scalar_one_or_none.return_value = value
    return m


class StopKeywordTests(unittest.TestCase):
    def test_exact_allowlist(self):
        self.assertTrue(is_transactional_stop_keyword("STOP"))
        self.assertTrue(is_transactional_stop_keyword("  berhenti "))
        self.assertTrue(is_transactional_stop_keyword("Berhenti"))
        self.assertFalse(is_transactional_stop_keyword("BATAL"))
        self.assertFalse(is_transactional_stop_keyword("batal dong"))
        self.assertFalse(is_transactional_stop_keyword("please STOP"))
        self.assertFalse(is_transactional_stop_keyword(""))
        self.assertFalse(is_transactional_stop_keyword(None))


class ApplyStopTests(unittest.IsolatedAsyncioTestCase):
    async def test_creates_suppression_withdraws_and_cancels_pre_network(self):
        seller_id = 9
        subject_id = uuid.uuid4()
        opp_id = uuid.uuid4()
        fingerprint = "fp-abc"

        fp = SimpleNamespace(contact_subject_id=subject_id, fingerprint=fingerprint)
        dispatch = SimpleNamespace(
            id=uuid.uuid4(),
            seller_id=seller_id,
            contact_subject_id=subject_id,
            opportunity_id=opp_id,
            status="pending",
            last_error_code=None,
        )
        opportunity = SimpleNamespace(
            id=opp_id,
            seller_id=seller_id,
            order_id=55,
            status="dispatch_pending",
            suppression_code=None,
            terminal_reason_code=None,
            state_version=1,
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _result(fp),  # fingerprint resolve
                _result(None),  # existing suppression
                _result([(55,)], many=True),  # order ids
                _result([dispatch], many=True),  # dispatches
                _result([opportunity], many=True),  # opportunities
            ]
        )
        db.flush = AsyncMock()
        db.add = MagicMock()

        with patch(
            "services.payment_recovery.opt_out.normalize_indonesian_phone",
            return_value=SimpleNamespace(status="valid", e164="+6281234567890"),
        ), patch(
            "services.payment_recovery.opt_out.hmac_fingerprint",
            return_value=(fingerprint, 1),
        ), patch(
            "services.payment_recovery.opt_out.withdraw_consent",
            new=AsyncMock(return_value=2),
        ) as withdraw:
            result = await apply_transactional_stop(
                db,
                seller_id=seller_id,
                channel="whatsapp",
                sender_phone="081234567890",
                source_event="wamid.stop1",
            )

        self.assertTrue(result["applied"])
        self.assertEqual(result["withdrawn_permissions"], 2)
        withdraw.assert_awaited_once()
        self.assertEqual(db.add.call_count, 1)
        self.assertEqual(dispatch.status, "cancelled")
        self.assertEqual(dispatch.last_error_code, "consent_withdrawn")
        self.assertEqual(opportunity.status, "suppressed")
        self.assertEqual(opportunity.suppression_code, "consent_withdrawn")
        self.assertEqual(opportunity.state_version, 2)

    async def test_does_not_cancel_accepted_or_in_flight(self):
        seller_id = 9
        subject_id = uuid.uuid4()
        fp = SimpleNamespace(contact_subject_id=subject_id, fingerprint="fp")
        accepted = SimpleNamespace(
            id=uuid.uuid4(),
            seller_id=seller_id,
            contact_subject_id=subject_id,
            opportunity_id=uuid.uuid4(),
            status="accepted",
            last_error_code=None,
        )
        in_flight = SimpleNamespace(
            id=uuid.uuid4(),
            seller_id=seller_id,
            contact_subject_id=subject_id,
            opportunity_id=uuid.uuid4(),
            status="request_in_flight",
            last_error_code=None,
        )
        unknown = SimpleNamespace(
            id=uuid.uuid4(),
            seller_id=seller_id,
            contact_subject_id=subject_id,
            opportunity_id=uuid.uuid4(),
            status="provider_unknown",
            last_error_code=None,
        )
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _result(fp),
                _result(SimpleNamespace(status="active")),  # suppression exists
                _result([], many=True),  # order ids
                _result([accepted, in_flight, unknown], many=True),  # dispatches
            ]
        )
        db.flush = AsyncMock()
        db.add = MagicMock()

        with patch(
            "services.payment_recovery.opt_out.normalize_indonesian_phone",
            return_value=SimpleNamespace(status="valid", e164="+628111"),
        ), patch(
            "services.payment_recovery.opt_out.hmac_fingerprint",
            return_value=("fp", 1),
        ), patch(
            "services.payment_recovery.opt_out.withdraw_consent",
            new=AsyncMock(return_value=0),
        ):
            result = await apply_transactional_stop(
                db,
                seller_id=seller_id,
                channel="whatsapp",
                sender_phone="08111",
            )

        self.assertTrue(result["applied"])
        self.assertEqual(accepted.status, "accepted")
        self.assertEqual(in_flight.status, "request_in_flight")
        self.assertEqual(unknown.status, "provider_unknown")
        db.add.assert_not_called()

    async def test_unknown_subject_is_noop(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[_result(None)])
        with patch(
            "services.payment_recovery.opt_out.normalize_indonesian_phone",
            return_value=SimpleNamespace(status="valid", e164="+628111"),
        ), patch(
            "services.payment_recovery.opt_out.hmac_fingerprint",
            return_value=("fp", 1),
        ):
            result = await apply_transactional_stop(
                db,
                seller_id=1,
                channel="whatsapp",
                sender_phone="08111",
            )
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "contact_subject_not_found")

    def test_webhook_wires_stop_keyword(self):
        import inspect
        from api import routes_webhooks

        source = inspect.getsource(routes_webhooks.whatsapp_cloud_webhook)
        self.assertIn("is_transactional_stop_keyword", source)
        self.assertIn("apply_transactional_stop", source)


if __name__ == "__main__":
    unittest.main()

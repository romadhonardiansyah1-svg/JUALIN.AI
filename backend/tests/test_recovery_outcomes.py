"""P5.1 — Honest recovery outcome ledger."""
from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from services.payment_recovery.outcomes import (
    RULE_VERSION,
    mark_expired_unpaid_if_due,
    record_verified_payment_outcome,
    reconcile_payment_for_opportunity,
)


def _scalar(value):
    m = MagicMock()
    m.scalar_one_or_none.return_value = value
    return m


class OutcomeRecordingTests(unittest.IsolatedAsyncioTestCase):
    async def test_payment_after_acceptance_is_observed_and_rule_attributed(self):
        seller_id = 3
        opp_id = uuid.uuid4()
        attempt_id = uuid.uuid4()
        dispatch_id = uuid.uuid4()
        accepted_at = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        paid_at = accepted_at + timedelta(hours=2)

        opportunity = SimpleNamespace(
            id=opp_id,
            seller_id=seller_id,
            order_id=99,
            payment_attempt_id=attempt_id,
            status="dispatched",
            state_version=2,
        )
        dispatch = SimpleNamespace(
            id=dispatch_id,
            status="accepted",
            accepted_at=accepted_at,
        )
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[_scalar(None)])  # no existing outcome
        db.add = MagicMock()
        db.flush = AsyncMock()

        result = await record_verified_payment_outcome(
            db,
            seller_id=seller_id,
            order_id=99,
            payment_attempt_id=attempt_id,
            opportunity=opportunity,
            dispatch=dispatch,
            amount="125000.50",
            observed_at=paid_at,
            source_event_key="payment:midtrans:inv-1",
        )

        self.assertTrue(result["applied"])
        self.assertTrue(result["after_acceptance"])
        self.assertTrue(result["attributed"])
        self.assertIsNone(result["causal_estimate"])
        self.assertEqual(opportunity.status, "payment_observed")
        self.assertEqual(opportunity.state_version, 3)
        # OutcomeEvent + AttributionAssessment
        self.assertEqual(db.add.call_count, 2)
        outcome = db.add.call_args_list[0].args[0]
        assessment = db.add.call_args_list[1].args[0]
        self.assertEqual(outcome.event_type, "payment_observed")
        self.assertEqual(outcome.amount, Decimal("125000.50"))
        self.assertEqual(assessment.method, "rule_attributed")
        self.assertEqual(assessment.rule_version, RULE_VERSION)

    async def test_payment_before_acceptance_not_observed_after_reminder(self):
        seller_id = 3
        attempt_id = uuid.uuid4()
        opportunity = SimpleNamespace(
            id=uuid.uuid4(),
            seller_id=seller_id,
            order_id=1,
            payment_attempt_id=attempt_id,
            status="dispatch_pending",
            state_version=1,
        )
        dispatch = SimpleNamespace(
            id=uuid.uuid4(),
            status="provider_unknown",
            accepted_at=None,
        )
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[_scalar(None)])
        db.add = MagicMock()
        db.flush = AsyncMock()

        result = await record_verified_payment_outcome(
            db,
            seller_id=seller_id,
            order_id=1,
            payment_attempt_id=attempt_id,
            opportunity=opportunity,
            dispatch=dispatch,
            amount=Decimal("10000.00"),
            observed_at=datetime.now(timezone.utc),
            source_event_key="payment:pre:1",
        )

        self.assertTrue(result["applied"])
        self.assertFalse(result["after_acceptance"])
        self.assertFalse(result["attributed"])
        self.assertEqual(opportunity.status, "dispatch_pending")
        self.assertEqual(db.add.call_count, 1)
        outcome = db.add.call_args.args[0]
        self.assertEqual(outcome.event_type, "payment_verified_pre_acceptance")

    async def test_duplicate_source_event_is_noop(self):
        existing = SimpleNamespace(id=uuid.uuid4())
        opportunity = SimpleNamespace(
            id=uuid.uuid4(),
            seller_id=1,
            order_id=1,
            payment_attempt_id=uuid.uuid4(),
            status="dispatched",
            state_version=1,
        )
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[_scalar(existing)])
        db.add = MagicMock()

        result = await record_verified_payment_outcome(
            db,
            seller_id=1,
            order_id=1,
            payment_attempt_id=opportunity.payment_attempt_id,
            opportunity=opportunity,
            dispatch=None,
            amount="1.00",
            observed_at=datetime.now(timezone.utc),
            source_event_key="dup",
        )
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "duplicate_source_event")
        db.add.assert_not_called()

    async def test_wrong_cycle_rejected(self):
        opportunity = SimpleNamespace(
            id=uuid.uuid4(),
            seller_id=1,
            order_id=1,
            payment_attempt_id=uuid.uuid4(),
            status="dispatched",
            state_version=1,
        )
        db = AsyncMock()
        result = await record_verified_payment_outcome(
            db,
            seller_id=1,
            order_id=1,
            payment_attempt_id=uuid.uuid4(),
            opportunity=opportunity,
            dispatch=None,
            amount="1.00",
            observed_at=datetime.now(timezone.utc),
            source_event_key="x",
        )
        self.assertEqual(result["reason"], "wrong_payment_cycle")

    async def test_expired_unpaid_requires_known_provider_state(self):
        db = AsyncMock()
        result = await mark_expired_unpaid_if_due(
            db,
            seller_id=1,
            opportunity_id=uuid.uuid4(),
            payment_expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            provider_state_known=False,
        )
        self.assertEqual(result["reason"], "provider_state_unknown")
        db.execute.assert_not_awaited()

    async def test_expired_unpaid_transitions_dispatched(self):
        opp = SimpleNamespace(
            status="dispatched",
            terminal_reason_code=None,
            state_version=3,
        )
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[_scalar(opp)])
        db.flush = AsyncMock()
        past = datetime.now(timezone.utc) - timedelta(days=1)
        result = await mark_expired_unpaid_if_due(
            db,
            seller_id=1,
            opportunity_id=uuid.uuid4(),
            payment_expires_at=past,
            provider_state_known=True,
        )
        self.assertTrue(result["applied"])
        self.assertEqual(opp.status, "expired_unpaid")
        self.assertEqual(opp.state_version, 4)

    async def test_reconcile_scopes_to_seller(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[_scalar(None)])
        result = await reconcile_payment_for_opportunity(
            db,
            seller_id=9,
            opportunity_id=uuid.uuid4(),
            amount="10.00",
            observed_at=datetime.now(timezone.utc),
            source_event_key="k",
        )
        self.assertEqual(result["reason"], "opportunity_not_found")


if __name__ == "__main__":
    unittest.main()

"""P4.5 — Recovery detail exposes exact digest for approval UI."""
from __future__ import annotations

import inspect
import unittest
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from starlette.requests import Request
from starlette.responses import Response

from api import routes_public_payments, routes_recovery


class RecoveryDetailContractTests(unittest.TestCase):
    def test_detail_loads_pending_approval_digest_not_placeholder(self):
        source = inspect.getsource(routes_recovery.get_opportunity_detail)
        self.assertIn("AgentApproval", source)
        self.assertIn("action_digest", source)
        self.assertIn("can_decide", source)
        self.assertNotIn("pending_approval_required_in_next_phase", source)

    def test_overview_reads_recovery_mode_from_settings(self):
        source = inspect.getsource(routes_recovery.get_overview)
        self.assertIn("PAYMENT_RECOVERY_MODE", source)
        self.assertNotIn('"mode": "observe",  # Phase 2 only observe', source)


class PublicPaymentExchangeTests(unittest.IsolatedAsyncioTestCase):
    async def test_exchange_returns_the_http_only_session_cookie(self):
        request = Request({
            "type": "http",
            "method": "POST",
            "path": "/api/public/payments/42/exchange",
            "headers": [],
        })
        db = AsyncMock()
        order_result = unittest.mock.MagicMock()
        order_result.scalar_one_or_none.return_value = SimpleNamespace(id=42)
        db.execute.return_value = order_result

        with (
            patch.object(routes_public_payments, "_verify_origin"),
            patch.object(routes_public_payments, "_rate_limit_public", new=AsyncMock()),
            patch.object(
                routes_public_payments,
                "verify_and_use_capability",
                new=AsyncMock(return_value=SimpleNamespace(id="capability")),
            ),
            patch.object(
                routes_public_payments,
                "create_capability_session",
                new=AsyncMock(return_value=(SimpleNamespace(id="session"), "session-token")),
            ),
        ):
            returned = await routes_public_payments.exchange_capability(
                42,
                routes_public_payments.ExchangeRequest(
                    bootstrap_token="bootstrap-token-long-enough"
                ),
                request,
                Response(),
                db,
            )

        cookies = returned.headers.getlist("set-cookie")
        self.assertEqual(len(cookies), 1)
        self.assertIn("payment_capability_session=session-token", cookies[0])
        self.assertIn("HttpOnly", cookies[0])
        self.assertIn("Path=/api/public/payments/42", cookies[0])


    async def test_impersonation_cannot_approve_or_reject_recovery(self):
        request = Request({"type": "http", "method": "POST", "path": "/"})
        request.state.auth_context = {
            "impersonation": True,
            "impersonated_by": 1,
            "target_seller_id": 42,
        }
        user = SimpleNamespace(id=42, role="seller")

        with self.assertRaises(routes_recovery.HTTPException) as approve_error:
            await routes_recovery.approve_opportunity(
                uuid.uuid4(),
                routes_recovery.ApproveRequest(
                    expected_version=1,
                    action_digest="digest",
                    idempotency_key="approve-key",
                ),
                request,
                user,
                AsyncMock(),
            )
        self.assertEqual(approve_error.exception.status_code, 403)

        with self.assertRaises(routes_recovery.HTTPException) as reject_error:
            await routes_recovery.reject_opportunity(
                uuid.uuid4(),
                routes_recovery.RejectRequest(
                    expected_version=1,
                    idempotency_key="reject-key",
                ),
                request,
                user,
                AsyncMock(),
            )
        self.assertEqual(reject_error.exception.status_code, 403)


    async def test_approval_mode_detector_materializes_detected_opportunities(self):
        import worker

        opportunity = SimpleNamespace(
            id=uuid.uuid4(), seller_id=42, policy_version=3
        )
        db = AsyncMock()
        detector = AsyncMock(return_value=[opportunity])
        materializer = AsyncMock(return_value=SimpleNamespace(id=9))

        @asynccontextmanager
        async def fake_session():
            yield db

        with (
            patch.object(worker.settings, "ENABLE_PAYMENT_RECOVERY", True),
            patch.object(worker.settings, "PAYMENT_RECOVERY_MODE", "approval"),
            patch.object(worker, "async_session", fake_session),
            patch(
                "services.payment_recovery.detector.detect_payment_recovery_opportunities",
                new=detector,
            ),
            patch(
                "services.payment_recovery.approval_materializer.materialize_approval_for_opportunity",
                new=materializer,
            ),
        ):
            await worker.cron_recovery_detector({})

        materializer.assert_awaited_once_with(
            db,
            seller_id=42,
            opportunity_id=opportunity.id,
            policy_version=3,
        )
        db.commit.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()

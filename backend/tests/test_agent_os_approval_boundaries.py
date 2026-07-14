"""
P0.6 — Prevent legacy approval bypass for recovery approvals.
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class LegacyApprovalBypassTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_list_excludes_recovery_action_type(self):
        from api.routes_agent_os import list_approvals, RESERVED_RECOVERY_ACTION_TYPES
        from models.agent_os import AgentApproval

        # Mock approvals: one normal, one recovery
        normal = MagicMock(spec=AgentApproval)
        normal.id = 1
        normal.seller_id = 10
        normal.agent_role = "negotiator"
        normal.action_type = "apply_discount"
        normal.title = "Normal"
        normal.detail_json = {}
        normal.status = "pending"
        normal.conversation_id = None
        normal.created_at = None
        normal.opportunity_id = None

        recovery = MagicMock(spec=AgentApproval)
        recovery.id = 2
        recovery.seller_id = 10
        recovery.agent_role = "growth"
        recovery.action_type = "payment_recovery"
        recovery.title = "Recovery"
        recovery.detail_json = {}
        recovery.status = "pending"
        recovery.conversation_id = None
        recovery.created_at = None
        recovery.opportunity_id = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [normal, recovery]
        mock_db.execute.return_value = mock_result

        current_user = MagicMock(id=10)

        # Call list_approvals — should filter out recovery
        result = await list_approvals(status="pending", current_user=current_user, db=mock_db)

        ids = [r["id"] for r in result]
        self.assertIn(1, ids)
        self.assertNotIn(2, ids, "Recovery approval should be excluded from legacy list")

    async def test_legacy_decide_rejects_recovery_action_type(self):
        from api.routes_agent_os import _decide_approval
        from models.agent_os import AgentApproval

        recovery = MagicMock(spec=AgentApproval)
        recovery.id = 99
        recovery.seller_id = 10
        recovery.action_type = "payment_recovery"
        recovery.opportunity_id = None
        recovery.status = "pending"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = recovery
        mock_db.execute.return_value = mock_result

        current_user = MagicMock(id=10)

        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as cm:
            await _decide_approval(approval_id=99, decision="approved", current_user=current_user, db=mock_db)

        self.assertEqual(cm.exception.status_code, 404)

    async def test_legacy_decide_rejects_opportunity_id_row(self):
        """Post-P2.1 guard: opportunity_id != NULL should also be blocked."""
        from api.routes_agent_os import _decide_approval, _is_recovery_approval
        from models.agent_os import AgentApproval

        # Simulate future model with opportunity_id
        rec = MagicMock()
        rec.id = 100
        rec.seller_id = 10
        rec.action_type = "apply_discount"  # even if not reserved, opportunity_id triggers block
        rec.opportunity_id = "some-uuid"
        rec.status = "pending"

        self.assertTrue(_is_recovery_approval(rec), "Row with opportunity_id should be considered recovery")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = rec
        mock_db.execute.return_value = mock_result

        current_user = MagicMock(id=10)

        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as cm:
            await _decide_approval(approval_id=100, decision="approved", current_user=current_user, db=mock_db)

        self.assertEqual(cm.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()

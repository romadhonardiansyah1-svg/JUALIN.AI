"""
P2.3 — Capability and global control tests.
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class CapabilityEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_capabilities_returns_no_store(self):
        from api.routes_system import get_capabilities

        mock_db = AsyncMock()

        # Mock control not exist
        mock_control_result = MagicMock()
        mock_control_result.scalar_one_or_none.return_value = None
        # Mock policy not exist
        mock_policy_result = MagicMock()
        mock_policy_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_control_result, mock_policy_result]

        current_user = MagicMock(id=42)

        response = await get_capabilities(current_user=current_user, db=mock_db)

        # Should be JSONResponse with no-store header
        self.assertEqual(response.headers.get("Cache-Control"), "private, no-store")
        import json
        body = json.loads(response.body)
        self.assertIn("capabilities", body)
        self.assertIn("payment_recovery", body["capabilities"])

    async def test_capabilities_combine_env_global_tenant(self):
        from api.routes_system import get_capabilities

        mock_db = AsyncMock()

        # Control enabled but paused
        mock_control = MagicMock()
        mock_control.enabled = True
        mock_control.paused = True
        mock_control.version = 2

        mock_control_result = MagicMock()
        mock_control_result.scalar_one_or_none.return_value = mock_control

        # Tenant policy observe and paused
        mock_policy = MagicMock()
        mock_policy.payment_recovery_mode = "approval"
        mock_policy.payment_recovery_paused = True
        mock_policy.version = 3

        mock_policy_result = MagicMock()
        mock_policy_result.scalar_one_or_none.return_value = mock_policy

        mock_db.execute.side_effect = [mock_control_result, mock_policy_result]

        current_user = MagicMock(id=42)

        with patch("api.routes_system.settings") as mock_settings:
            mock_settings.ENABLE_PAYMENT_RECOVERY = True
            mock_settings.PAYMENT_RECOVERY_MODE = "approval"

            response = await get_capabilities(current_user=current_user, db=mock_db)
            import json
            body = json.loads(response.body)
            cap = body["capabilities"]["payment_recovery"]
            # Global paused -> effective paused true, enabled false
            self.assertTrue(cap["paused"])
            self.assertFalse(cap["enabled"])


if __name__ == "__main__":
    unittest.main()

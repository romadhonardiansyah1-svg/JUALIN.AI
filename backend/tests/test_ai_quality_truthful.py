"""
P0.5 / P5.4 — Truthful AI eval: no orphan jobs, offline recovery eval only.
"""
import unittest
from unittest.mock import AsyncMock, MagicMock


class AIQualityEvalTests(unittest.IsolatedAsyncioTestCase):
    async def test_eval_run_is_offline_and_creates_no_orphan_job(self):
        from api.routes_ai_quality import run_eval

        mock_db = AsyncMock()
        user = MagicMock(id=1)

        result = await run_eval(current_user=user, db=mock_db)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["mode"], "offline_deterministic")
        self.assertEqual(result["capability"], "recovery_variant_eval")
        self.assertIn("report", result)
        self.assertEqual(result["report"]["failed"], 0)
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()

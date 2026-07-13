"""
P0.5 — Truthful AI placeholder and dashboard claims.
"""
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException


class AIQualityPlaceholderTests(unittest.IsolatedAsyncioTestCase):
    async def test_eval_placeholder_returns_501_and_no_job(self):
        from api.routes_ai_quality import run_eval_placeholder
        from models.ai_quality import AIEvalCase, AIEvalRun

        # Mock DB
        mock_db = AsyncMock()

        # We should ensure no AIEvalRun is added to DB
        # The function should raise HTTPException 501 before any DB write

        with self.assertRaises(HTTPException) as cm:
            await run_eval_placeholder(current_user=MagicMock(id=1), db=mock_db)

        self.assertEqual(cm.exception.status_code, 501)
        # Ensure db.add was not called (no orphan job)
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()

        # Check detail contains not_implemented
        detail = cm.exception.detail
        if isinstance(detail, dict):
            self.assertIn("not_implemented", str(detail).lower() or detail.get("error", ""))
        else:
            self.assertIn("not_implemented", str(detail).lower())


if __name__ == "__main__":
    unittest.main()

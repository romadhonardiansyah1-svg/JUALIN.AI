"""P5.4 — Offline recovery AI eval suite."""
from __future__ import annotations

import unittest

from services.payment_recovery.ai_eval import run_recovery_variant_eval


class RecoveryAiEvalTests(unittest.TestCase):
    def test_offline_eval_all_cases_pass(self):
        report = run_recovery_variant_eval()
        self.assertEqual(report["dataset_version"], "recovery_variant_eval_v1")
        self.assertGreater(report["total"], 0)
        self.assertEqual(report["failed"], 0)
        self.assertEqual(report["passed"], report["total"])
        self.assertTrue(report["static_baseline_ok"])
        self.assertIn("Does not claim model superiority", report["disclaimer"])
        # Unsafe outputs blocked
        self.assertGreaterEqual(report["prohibited_output_blocked"], 3)


if __name__ == "__main__":
    unittest.main()

"""P6.1/P6.2 — Proof Mode harness."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.payment_recovery.proof import (
    SCENARIOS,
    run_all,
    run_scenario,
)


class ProofModeTests(unittest.TestCase):
    def test_every_scenario_has_assertions_and_can_pass(self):
        for sid in SCENARIOS:
            with self.subTest(scenario=sid):
                result = run_scenario(sid, seed=42)
                self.assertIn(result.status, {"passed", "failed", "blocked"})
                self.assertGreater(len(result.assertions), 0)
                self.assertEqual(result.status, "passed", msg=result.assertions)

    def test_unknown_scenario_fails_not_premarked_pass(self):
        result = run_scenario("does-not-exist", seed=1)
        self.assertEqual(result.status, "failed")
        self.assertFalse(all(a["ok"] for a in result.assertions))

    def test_run_all_writes_evidence_with_commit(self):
        payload = run_all(seed=42, suite="backend")
        self.assertIn(payload["status"], {"passed", "failed", "blocked"})
        self.assertEqual(payload["summary"]["total"], len(SCENARIOS))
        self.assertEqual(payload["summary"]["passed"], len(SCENARIOS))
        self.assertTrue(payload["commit_sha"])
        self.assertNotEqual(payload["commit_sha"], "")
        self.assertIn("Does not prove live", payload["disclaimer"])

    def test_cli_run_all_exit_zero(self):
        from scripts.proof_mode import main

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "proof-backend.json"
            code = main(["run-all", "--suite", "backend", "--seed", "42", "--output", str(out)])
            self.assertEqual(code, 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "passed")
            self.assertEqual(data["summary"]["failed"], 0)

    def test_production_guard_blocks(self):
        with patch.dict(
            os.environ,
            {"ENVIRONMENT": "production", "ENABLE_DEMO_PROOF_MODE": "true"},
            clear=False,
        ):
            result = run_scenario("duplicate-webhook", seed=1)
        self.assertEqual(result.status, "blocked")


if __name__ == "__main__":
    unittest.main()

"""P6.1/P6.2 — Proof Mode harness coverage."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.payment_recovery.proof import (
    BROWSER_SCENARIO_ID,
    REQUIRED_BACKEND_SCENARIOS,
    SCENARIOS,
    run_all,
    run_scenario,
)


class ProofModeTests(unittest.TestCase):
    def test_all_required_backend_scenarios_registered(self):
        for sid in REQUIRED_BACKEND_SCENARIOS:
            self.assertIn(sid, SCENARIOS)

    def test_every_backend_scenario_has_assertions_and_passes(self):
        for sid in REQUIRED_BACKEND_SCENARIOS:
            with self.subTest(scenario=sid):
                result = run_scenario(sid, seed=42)
                self.assertEqual(result.status, "passed", msg=result.assertions)
                self.assertGreater(len(result.assertions), 0)

    def test_browser_scenario_is_not_run_by_backend(self):
        result = run_scenario(BROWSER_SCENARIO_ID, seed=1)
        self.assertEqual(result.status, "not_run")
        self.assertEqual(result.assertions, [])

    def test_unknown_scenario_fails_not_premarked_pass(self):
        result = run_scenario("does-not-exist", seed=1)
        self.assertEqual(result.status, "failed")

    def test_run_all_backend_dimensions_separate(self):
        payload = run_all(seed=42, suite="backend")
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["dimensions"]["backend_invariants"], "passed")
        self.assertEqual(payload["dimensions"]["browser_e2e"], "not_run")
        self.assertEqual(payload["dimensions"]["staging_provider"], "blocked")
        self.assertEqual(payload["summary"]["backend_passed"], len(REQUIRED_BACKEND_SCENARIOS))
        self.assertTrue(payload["commit_sha"])
        self.assertEqual(payload["missing_required"], [])
        self.assertEqual(payload["empty_assertion_failures"], [])

    def test_cli_run_all_exit_zero(self):
        from scripts.proof_mode import main

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "proof-backend.json"
            code = main(["run-all", "--suite", "backend", "--seed", "42", "--output", str(out)])
            self.assertEqual(code, 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "passed")
            self.assertEqual(data["dimensions"]["browser_e2e"], "not_run")

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

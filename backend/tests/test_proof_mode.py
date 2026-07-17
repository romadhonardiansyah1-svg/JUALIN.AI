"""P6.1/P6.2 — Proof Mode harness coverage."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from services.payment_recovery.proof import (
    BROWSER_SCENARIO_ID,
    REQUIRED_BACKEND_SCENARIOS,
    SCENARIOS,
    run_all,
    run_scenario,
)


class ProofModeTests(unittest.TestCase):
    def setUp(self):
        self._settings_patch = patch(
            "services.payment_recovery.proof.get_settings",
            return_value=SimpleNamespace(
                WHATSAPP_ACCESS_TOKEN="",
                WHATSAPP_PHONE_NUMBER_ID="",
                WHATSAPP_WABA_ID="",
                WHATSAPP_APP_SECRET="",
                WHATSAPP_VERIFY_TOKEN="",
            ),
            create=True,
        )
        self._settings_patch.start()
        self.addCleanup(self._settings_patch.stop)

    def test_all_required_backend_scenarios_registered(self):
        for sid in REQUIRED_BACKEND_SCENARIOS:
            self.assertIn(sid, SCENARIOS)

    def test_every_backend_scenario_has_assertions_and_passes(self):
        for sid in REQUIRED_BACKEND_SCENARIOS:
            with self.subTest(scenario=sid):
                result = run_scenario(sid, seed=42)
                self.assertEqual(result.status, "passed", msg=result.assertions)
                self.assertGreater(len(result.assertions), 0)

    def test_quiet_hours_proof_rejects_allowed_result(self):
        with patch(
            "services.payment_recovery.proof.resolve_quiet_hours",
            return_value=("allowed", "ok"),
        ):
            result = run_scenario("quiet-hours-expiry", seed=1)

        self.assertEqual(result.status, "failed")

    def test_browser_scenario_is_not_run_by_backend(self):
        result = run_scenario(BROWSER_SCENARIO_ID, seed=1)
        self.assertEqual(result.status, "not_run")
        self.assertEqual(result.assertions, [])

    def test_unknown_scenario_fails_not_premarked_pass(self):
        result = run_scenario("does-not-exist", seed=1)
        self.assertEqual(result.status, "failed")


    def test_stale_approval_fails_when_production_digest_breaks(self):
        with patch(
            "services.payment_recovery.actions.action_digest",
            side_effect=RuntimeError("digest unavailable"),
        ):
            result = run_scenario("stale-approval", seed=1)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.details["error_type"], "RuntimeError")

    def test_run_all_backend_dimensions_separate(self):
        with (
            patch("services.payment_recovery.proof._git_commit_sha", return_value="abc"),
            patch("services.payment_recovery.proof.git_source_tree_clean", return_value=True),
        ):
            payload = run_all(seed=42, suite="backend")
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["dimensions"]["backend_invariants"], "passed")
        self.assertEqual(payload["dimensions"]["browser_e2e"], "not_run")
        self.assertEqual(payload["dimensions"]["staging_provider"], "blocked")
        self.assertEqual(payload["summary"]["backend_passed"], len(REQUIRED_BACKEND_SCENARIOS))
        self.assertTrue(payload["commit_sha"])
        self.assertEqual(payload["missing_required"], [])
        self.assertEqual(payload["empty_assertion_failures"], [])

    def test_run_all_uses_explicit_evidence_run_identity(self):
        with patch.dict(
            os.environ,
            {"JUALIN_EVIDENCE_RUN_ID": "ci-123-1"},
            clear=False,
        ):
            payload = run_all(seed=42, suite="backend")

        self.assertEqual(payload["run_id"], "ci-123-1")
        self.assertEqual(payload["seed"], 42)

    def test_run_all_records_dirty_source_tree(self):
        with patch(
            "services.payment_recovery.proof.git_source_tree_clean",
            return_value=False,
        ):
            payload = run_all(seed=42, suite="backend")

        self.assertIs(payload["source_tree_clean"], False)
        self.assertEqual(payload["status"], "unverified")

    def test_cli_run_all_exit_zero(self):
        from scripts.proof_mode import main

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "proof-backend.json"
            with (
                patch("services.payment_recovery.proof._git_commit_sha", return_value="abc"),
                patch("services.payment_recovery.proof.git_source_tree_clean", return_value=True),
            ):
                code = main(["run-all", "--suite", "backend", "--seed", "42", "--output", str(out)])
            self.assertEqual(code, 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "passed")
            self.assertEqual(data["dimensions"]["browser_e2e"], "not_run")

    def test_production_guard_blocks(self):
        cases = (
            {"ENVIRONMENT": "production"},
            {"APP_ENV": "production"},
            {"ENVIRONMENT": "development", "APP_ENV": "production"},
            {"ENVIRONMENT": " production "},
            {"WHATSAPP_ACCESS_TOKEN": "synthetic-provider-credential"},
        )
        for environment in cases:
            with self.subTest(environment=environment):
                with patch.dict(os.environ, environment, clear=True):
                    result = run_scenario("duplicate-webhook", seed=1)
                self.assertEqual(result.status, "blocked")

        configured = SimpleNamespace(
            WHATSAPP_ACCESS_TOKEN="configured-provider-credential",
            WHATSAPP_PHONE_NUMBER_ID="",
            WHATSAPP_WABA_ID="",
            WHATSAPP_APP_SECRET="",
            WHATSAPP_VERIFY_TOKEN="",
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "services.payment_recovery.proof.get_settings",
                return_value=configured,
                create=True,
            ),
        ):
            result = run_scenario("duplicate-webhook", seed=1)
        self.assertEqual(result.status, "blocked")


if __name__ == "__main__":
    unittest.main()

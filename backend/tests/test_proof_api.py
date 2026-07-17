"""P6.3 hardened Proof Mode API contracts."""
from __future__ import annotations

import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from pydantic import ValidationError


class ProofApiContractTests(unittest.TestCase):
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

    def test_routes_registered(self):
        import main

        paths = {getattr(r, "path", "") for r in main.app.routes}
        self.assertTrue(any("/api/proof/run" in p for p in paths))
        self.assertTrue(any("/api/proof/download" in p for p in paths))

    def test_seller_without_demo_flag_forbidden(self):
        from api.routes_proof import _require_proof_principal
        from models.user import UserRole

        with patch("api.routes_proof._production_proof_disabled", return_value=False):
            with patch("api.routes_proof.settings") as s:
                s.ENABLE_DEMO_PROOF_MODE = False
                user = SimpleNamespace(role=UserRole.SELLER, id=2)
                with self.assertRaises(HTTPException) as cm:
                    _require_proof_principal(user)
                self.assertEqual(cm.exception.status_code, 403)

    def test_production_returns_404(self):
        from api.routes_proof import _require_proof_principal
        from models.user import UserRole

        with patch("api.routes_proof._production_proof_disabled", return_value=True):
            user = SimpleNamespace(role=UserRole.ADMIN, id=1)
            with self.assertRaises(HTTPException) as cm:
                _require_proof_principal(user)
            self.assertEqual(cm.exception.status_code, 404)

    def test_request_forbids_extra_fields(self):
        from api.routes_proof import ProofRunRequest

        with self.assertRaises(ValidationError):
            ProofRunRequest(suite="backend", seed=1, dsn="postgresql://x")
        with self.assertRaises(ValidationError):
            ProofRunRequest(suite="backend", seed=1, path="/etc/passwd")
        with self.assertRaises(ValidationError):
            ProofRunRequest(suite="evil", seed=1)

    def test_arbitrary_scenario_rejected_by_allowlist(self):
        from api.routes_proof import REQUIRED_BACKEND_SCENARIOS

        self.assertNotIn("rm -rf /", REQUIRED_BACKEND_SCENARIOS)
        self.assertNotIn("os.system", REQUIRED_BACKEND_SCENARIOS)

    def test_download_name_allowlist(self):
        from api.routes_proof import _artifact_path

        with self.assertRaises(HTTPException):
            _artifact_path("../.env")
        with self.assertRaises(HTTPException):
            _artifact_path("C:/secrets.json")
        p = _artifact_path("proof-backend-latest.json")
        self.assertEqual(p.name, "proof-backend-latest.json")

    def test_stale_commit_marks_unverified(self):
        from api.routes_proof import _stale_status, SCHEMA_VERSION

        data = {
            "commit_sha": "deadbeef",
            "schema_version": SCHEMA_VERSION,
            "status": "passed",
        }
        with (
            patch("api.routes_proof._git_commit_sha", return_value="cafebabe"),
            patch("api.routes_proof.git_source_tree_clean", return_value=True),
        ):
            self.assertEqual(_stale_status(data), "commit_mismatch")

    def test_latest_downgrades_unverifiable_backend_pass(self):
        import asyncio

        from api.routes_proof import proof_latest
        from services.payment_recovery.proof import run_all

        cases = (
            (
                "artifact dirty",
                lambda payload: payload.update(source_tree_clean=False),
                "source_tree_dirty",
                "abc",
                True,
            ),
            (
                "timestamps reversed",
                lambda payload: payload.update(
                    started_at="2026-07-17T00:02:00+00:00",
                    finished_at="2026-07-17T00:01:00+00:00",
                ),
                "invalid_time_window",
                "abc",
                True,
            ),
            (
                "suite missing",
                lambda payload: payload.pop("suite"),
                "backend_suite_mismatch",
                "abc",
                True,
            ),
            (
                "current tree dirty",
                lambda payload: None,
                "current_source_tree_dirty",
                "abc",
                False,
            ),
            (
                "current commit unknown",
                lambda payload: None,
                "current_commit_unknown",
                "unknown",
                True,
            ),
            (
                "schema missing",
                lambda payload: payload.pop("schema_version"),
                "missing_schema_version",
                "abc",
                True,
            ),
            (
                "redaction metadata failed",
                lambda payload: payload.update(redaction_status="failed"),
                "artifact_redaction_unverified",
                "abc",
                True,
            ),
            (
                "assertion message missing",
                lambda payload: payload["scenarios"][0]["assertions"][0].pop(
                    "message", None
                ),
                "backend_assertions_invalid",
                "abc",
                True,
            ),
            (
                "assertion inventory replaced",
                lambda payload: payload["scenarios"][0].update(
                    assertions=[{"ok": True, "message": "tautology"}]
                ),
                "backend_assertions_invalid",
                "abc",
                True,
            ),
            (
                "failed artifact with dirty recorded source",
                lambda payload: payload.update(status="failed", source_tree_clean=False),
                "source_tree_dirty",
                "abc",
                True,
            ),
            (
                "arbitrary status",
                lambda payload: payload.update(status="production_approved"),
                "invalid_artifact_status",
                "abc",
                True,
            ),
            (
                "backend dimensions malformed",
                lambda payload: payload.update(dimensions=["passed"]),
                "backend_metadata_invalid",
                "abc",
                True,
            ),
            (
                "run identity missing",
                lambda payload: payload.pop("run_id"),
                "backend_identity_missing",
                "abc",
                True,
            ),
        )
        with tempfile.TemporaryDirectory() as td:
            artifact = Path(td) / "proof-backend-latest.json"
            for label, mutate, expected_reason, current_commit, current_clean in cases:
                with self.subTest(case=label):
                    payload = run_all(seed=42, suite="backend")
                    payload.update(
                        {
                            "commit_sha": "abc",
                            "source_tree_clean": True,
                            "redaction_status": "passed",
                            "status": "passed",
                        }
                    )
                    mutate(payload)
                    artifact.write_text(json.dumps(payload), encoding="utf-8")
                    with (
                        patch("api.routes_proof._artifact_path", return_value=artifact),
                        patch("api.routes_proof._require_proof_principal"),
                        patch(
                            "api.routes_proof._git_commit_sha",
                            return_value=current_commit,
                        ),
                        patch(
                            "api.routes_proof.git_source_tree_clean",
                            return_value=current_clean,
                        ),
                    ):
                        response = asyncio.run(
                            proof_latest(current_user=SimpleNamespace(id=1))
                        )

                    body = json.loads(response.body)
                    self.assertEqual(body["status"], "UNVERIFIED")
                    self.assertEqual(body["verification_status"], "UNVERIFIED")
                    self.assertEqual(body["unverified_reason"], expected_reason)

    def test_run_rejects_sensitive_payload_before_persisting(self):
        import asyncio

        from api.routes_proof import ProofRunRequest, proof_run
        from models.user import UserRole

        unsafe_payload = {
            "suite": "backend",
            "status": "failed",
            "commit_sha": "abc",
            "schema_version": "proof-artifact-v1",
            "openai_api_key": "synthetic-sensitive-value",
        }
        with tempfile.TemporaryDirectory() as td:
            artifact = Path(td) / "proof-backend-latest.json"
            with (
                patch("api.routes_proof._require_proof_principal"),
                patch("api.routes_proof._check_rate_limit"),
                patch("api.routes_proof.production_guard_blocks_proof_mode", return_value=(False, "ok")),
                patch("api.routes_proof._is_production", return_value=False),
                patch("api.routes_proof.run_all", return_value=unsafe_payload),
                patch("api.routes_proof._artifact_path", return_value=artifact),
                patch("api.routes_proof._git_commit_sha", return_value="abc"),
                patch("api.routes_proof.git_source_tree_clean", return_value=True),
            ):
                with self.assertRaises(ValueError):
                    asyncio.run(
                        proof_run(
                            ProofRunRequest(),
                            request=SimpleNamespace(query_params={}),
                            current_user=SimpleNamespace(id=1, role=UserRole.ADMIN),
                            db=None,
                        )
                    )

            self.assertFalse(artifact.exists())

    def test_latest_returns_unverified_envelope_for_malformed_artifact(self):
        import asyncio

        from api.routes_proof import proof_latest

        with tempfile.TemporaryDirectory() as td:
            artifact = Path(td) / "proof-backend-latest.json"
            artifact.write_text("{malformed", encoding="utf-8")
            with (
                patch("api.routes_proof._artifact_path", return_value=artifact),
                patch("api.routes_proof._require_proof_principal"),
            ):
                response = asyncio.run(
                    proof_latest(current_user=SimpleNamespace(id=1))
                )

        body = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["status"], "UNVERIFIED")
        self.assertEqual(body["verification_status"], "UNVERIFIED")
        self.assertEqual(body["unverified_reason"], "artifact_unreadable")


class EvidenceCollectorTests(unittest.TestCase):
    def setUp(self):
        self._source_tree_patch = patch(
            "services.payment_recovery.evidence_collector.git_source_tree_clean",
            return_value=True,
            create=True,
        )
        self._source_tree_patch.start()
        self.addCleanup(self._source_tree_patch.stop)
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

    def _write_browser_artifact(self, directory: Path, **overrides):
        browser_assertions = [
            {
                "ok": True,
                "message": f"Playwright passed: {title}",
                "audit_code": "real_browser_runtime",
            }
            for title in (
                "real auth tenant switch clears A before B",
                "real public capability exchange establishes an HttpOnly session",
                "real approval creates a durable dispatch",
            )
        ]
        worker_assertions = [
            {
                "ok": True,
                "message": "real approval created a durable PostgreSQL dispatch and job",
                "audit_code": "approval_to_dispatch_real_db",
            },
            {
                "ok": True,
                "message": "real worker claim stopped before provider at the global kill switch",
                "audit_code": "worker_pre_send_revalidation",
            },
        ]
        payload = {
            "schema_version": "proof-artifact-v1",
            "suite": "browser",
            "run_id": "shared-evidence-run",
            "seed": 42,
            "commit_sha": "abc",
            "status": "passed",
            "started_at": "2026-07-17T00:00:00+00:00",
            "finished_at": "2026-07-17T00:01:00+00:00",
            "redaction_status": "passed",
            "api_mocking": False,
            "source_tree_clean": True,
            "command": "python -m scripts.run_disposable_browser_e2e",
            "environment": "local_disposable",
            "dimensions": {
                "backend_invariants": "not_in_this_artifact",
                "browser_e2e": "passed",
                "backend_api": "passed",
                "postgresql": "passed",
                "redis": "passed",
                "worker_execution": "passed",
                "staging_provider": "blocked",
            },
            "infrastructure": {
                "loopback_only": True,
                "postgresql": "guarded_disposable_tmpfs",
                "redis": "guarded_disposable_no_persistence",
                "migration_rehearsal": "20260717_0012_downgrade_reupgrade_passed",
            },
            "disclaimer": (
                "Focused real local browser/backend/PostgreSQL/Redis proof with synthetic data. "
                "No live payment or messaging provider was called. DATA SIMULASI."
            ),
            "scenarios": [
                {
                    "scenario_id": "real-browser-disposable-stack",
                    "status": "passed",
                    "assertions": browser_assertions,
                    "provider_calls": 0,
                },
                {
                    "scenario_id": "approval-dispatch-worker-kill-switch",
                    "status": "passed",
                    "assertions": worker_assertions,
                    "provider_calls": 0,
                },
            ],
            "summary": {"total": 5, "passed": 5, "failed": 0},
        }
        payload.update(overrides)
        (directory / "proof-browser.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def _write_backend_artifact(self, directory: Path, **overrides):
        from services.payment_recovery.proof import run_all

        with patch.dict(
            os.environ,
            {"JUALIN_EVIDENCE_RUN_ID": "shared-evidence-run"},
            clear=False,
        ):
            payload = run_all(seed=42, suite="backend")
        payload["commit_sha"] = "abc"
        payload["source_tree_clean"] = True
        payload["status"] = "passed"
        payload.update(overrides)
        (directory / "proof-backend.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def test_assertion_free_backend_artifact_is_unverified(self):
        from services.payment_recovery.evidence_collector import evaluate_backend_proof

        with tempfile.TemporaryDirectory() as td:
            artifacts = Path(td)
            self._write_backend_artifact(
                artifacts,
                scenarios=[],
                required_backend_scenarios=[],
                summary={
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                    "blocked": 0,
                    "skipped": 0,
                    "not_run": 0,
                    "unverified": 0,
                    "backend_required": 0,
                    "backend_passed": 0,
                },
            )
            with patch(
                "services.payment_recovery.evidence_collector.ARTIFACTS",
                artifacts,
            ):
                evaluation = evaluate_backend_proof(current_commit="abc")

        self.assertEqual(evaluation.status, "unverified")
        self.assertEqual(evaluation.reason, "backend_assertions_invalid")

    def test_dirty_source_tree_artifacts_are_unverified(self):
        from services.payment_recovery.evidence_collector import (
            evaluate_backend_proof,
            evaluate_browser_proof,
        )

        with tempfile.TemporaryDirectory() as td:
            artifacts = Path(td)
            self._write_backend_artifact(artifacts, source_tree_clean=False)
            self._write_browser_artifact(artifacts, source_tree_clean=False)
            with patch(
                "services.payment_recovery.evidence_collector.ARTIFACTS",
                artifacts,
            ):
                backend = evaluate_backend_proof(current_commit="abc")
                browser = evaluate_browser_proof(current_commit="abc")

        self.assertEqual(backend.status, "unverified")
        self.assertIn("source_tree_dirty", backend.reason)
        self.assertEqual(browser.status, "unverified")
        self.assertEqual(browser.reason, "source_tree_dirty")

    def test_current_dirty_source_tree_cannot_verify_clean_artifacts(self):
        from services.payment_recovery.evidence_collector import (
            evaluate_backend_proof,
            evaluate_browser_proof,
        )

        with tempfile.TemporaryDirectory() as td:
            artifacts = Path(td)
            self._write_backend_artifact(artifacts, source_tree_clean=True)
            self._write_browser_artifact(artifacts, source_tree_clean=True)
            with (
                patch("services.payment_recovery.evidence_collector.ARTIFACTS", artifacts),
                patch(
                    "services.payment_recovery.evidence_collector.git_source_tree_clean",
                    return_value=False,
                    create=True,
                ),
            ):
                backend = evaluate_backend_proof(current_commit="abc")
                browser = evaluate_browser_proof(current_commit="abc")

        self.assertEqual(backend.status, "unverified")
        self.assertIn("current_source_tree_dirty", backend.reason)
        self.assertEqual(browser.status, "unverified")
        self.assertEqual(browser.reason, "current_source_tree_dirty")

    def test_invalid_or_reversed_artifact_times_are_unverified(self):
        from services.payment_recovery.evidence_collector import (
            evaluate_backend_proof,
            evaluate_browser_proof,
        )

        with tempfile.TemporaryDirectory() as td:
            artifacts = Path(td)
            self._write_backend_artifact(
                artifacts,
                started_at="not-a-timestamp",
                finished_at="2026-07-17T00:01:00+00:00",
            )
            self._write_browser_artifact(
                artifacts,
                started_at="2026-07-17T00:02:00+00:00",
                finished_at="2026-07-17T00:01:00+00:00",
            )
            with patch(
                "services.payment_recovery.evidence_collector.ARTIFACTS",
                artifacts,
            ):
                backend = evaluate_backend_proof(current_commit="abc")
                browser = evaluate_browser_proof(current_commit="abc")

        self.assertEqual(backend.status, "unverified")
        self.assertIn("invalid_time_window", backend.reason)
        self.assertEqual(browser.status, "unverified")
        self.assertEqual(browser.reason, "invalid_time_window")

    def test_missing_browser_is_not_run_not_verified(self):
        from services.payment_recovery.evidence_collector import evaluate_browser_proof

        with tempfile.TemporaryDirectory() as td:
            with patch(
                "services.payment_recovery.evidence_collector.ARTIFACTS",
                Path(td),
            ):
                ev = evaluate_browser_proof(current_commit="abc")
        self.assertEqual(ev.status, "not_run")
        self.assertEqual(ev.reason, "missing_artifact")

    def test_unreadable_browser_preserves_collection_failure_reason(self):
        from services.payment_recovery.evidence_collector import evaluate_browser_proof

        with tempfile.TemporaryDirectory() as td:
            artifacts = Path(td)
            (artifacts / "proof-browser.json").write_text("not-json", encoding="utf-8")
            with patch(
                "services.payment_recovery.evidence_collector.ARTIFACTS",
                artifacts,
            ):
                ev = evaluate_browser_proof(current_commit="abc")

        self.assertEqual(ev.status, "unverified")
        self.assertEqual(ev.reason, "read_failed")

    def test_existing_not_run_browser_with_failed_redaction_is_unverified(self):
        from services.payment_recovery.evidence_collector import evaluate_browser_proof

        with tempfile.TemporaryDirectory() as td:
            artifacts = Path(td)
            self._write_browser_artifact(
                artifacts,
                status="not_run",
                redaction_status="failed",
            )
            with patch(
                "services.payment_recovery.evidence_collector.ARTIFACTS",
                artifacts,
            ):
                evaluation = evaluate_browser_proof(current_commit="abc")

        self.assertEqual(evaluation.status, "unverified")
        self.assertEqual(evaluation.reason, "browser_redaction_unverified")

    def test_browser_with_non_object_dimensions_is_unverified(self):
        from services.payment_recovery.evidence_collector import evaluate_browser_proof

        with tempfile.TemporaryDirectory() as td:
            artifacts = Path(td)
            self._write_browser_artifact(artifacts, dimensions=["invalid"])
            with patch(
                "services.payment_recovery.evidence_collector.ARTIFACTS",
                artifacts,
            ):
                evaluation = evaluate_browser_proof(current_commit="abc")

        self.assertEqual(evaluation.status, "unverified")
        self.assertEqual(evaluation.reason, "browser_metadata_invalid")

    def test_artifact_sanitizer_rejects_sensitive_capability_keys(self):
        from services.payment_recovery.proof import load_sanitized_artifact

        with tempfile.TemporaryDirectory() as td:
            artifact = Path(td) / "unsafe.json"
            artifact.write_text(
                json.dumps({"payment_capability_token": "synthetic-secret-value"}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_sanitized_artifact(artifact)

    def test_artifact_sanitizer_rejects_api_key_fields(self):
        from services.payment_recovery.proof import load_sanitized_artifact

        with tempfile.TemporaryDirectory() as td:
            artifact = Path(td) / "unsafe-api-key.json"
            artifact.write_text(
                json.dumps({"openai_api_key": "synthetic-sensitive-value"}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_sanitized_artifact(artifact)

    def test_artifact_sanitizer_rejects_camel_case_token_fields(self):
        from services.payment_recovery.proof import load_sanitized_artifact

        for field_name in ("authToken", "APIKey"):
            with self.subTest(field_name=field_name):
                with tempfile.TemporaryDirectory() as td:
                    artifact = Path(td) / "unsafe-camel-case-token.json"
                    artifact.write_text(
                        json.dumps({field_name: "synthetic-sensitive-value"}),
                        encoding="utf-8",
                    )
                    with self.assertRaises(ValueError):
                        load_sanitized_artifact(artifact)

    def test_mocked_pass_artifact_cannot_be_promoted_to_verified(self):
        from services.payment_recovery.evidence_collector import evaluate_browser_proof

        with tempfile.TemporaryDirectory() as td:
            artifacts = Path(td)
            self._write_browser_artifact(
                artifacts,
                api_mocking=True,
                dimensions={
                    "browser_e2e": "mocked_unverified",
                    "staging_provider": "blocked",
                },
                disclaimer="Browser mocked-API proof.",
            )
            with patch(
                "services.payment_recovery.evidence_collector.ARTIFACTS",
                artifacts,
            ):
                ev = evaluate_browser_proof(current_commit="abc")

        self.assertEqual(ev.status, "unverified")
        self.assertEqual(ev.reason, "mocked_browser_artifact")

    def test_real_stack_artifact_requires_all_release_dimensions(self):
        from services.payment_recovery.evidence_collector import evaluate_browser_proof

        with tempfile.TemporaryDirectory() as td:
            artifacts = Path(td)
            self._write_browser_artifact(artifacts)
            with patch(
                "services.payment_recovery.evidence_collector.ARTIFACTS",
                artifacts,
            ):
                ev = evaluate_browser_proof(current_commit="abc")

        self.assertEqual(ev.status, "verified")
        self.assertEqual(ev.reason, "ok")

    def test_pass_artifact_without_commit_identity_is_unverified(self):
        from services.payment_recovery.evidence_collector import evaluate_browser_proof

        with tempfile.TemporaryDirectory() as td:
            artifacts = Path(td)
            self._write_browser_artifact(artifacts, commit_sha="")
            with patch(
                "services.payment_recovery.evidence_collector.ARTIFACTS",
                artifacts,
            ):
                ev = evaluate_browser_proof(current_commit="abc")

        self.assertEqual(ev.status, "unverified")
        self.assertEqual(ev.reason, "browser_identity_missing")

    def test_pass_artifact_with_inconsistent_summary_is_unverified(self):
        from services.payment_recovery.evidence_collector import evaluate_browser_proof

        with tempfile.TemporaryDirectory() as td:
            artifacts = Path(td)
            self._write_browser_artifact(
                artifacts,
                summary={"total": 2, "passed": 1, "failed": 1},
            )
            with patch(
                "services.payment_recovery.evidence_collector.ARTIFACTS",
                artifacts,
            ):
                ev = evaluate_browser_proof(current_commit="abc")

        self.assertEqual(ev.status, "unverified")
        self.assertEqual(ev.reason, "browser_summary_invalid")

    def test_pass_artifact_with_failed_assertion_is_unverified(self):
        from services.payment_recovery.evidence_collector import evaluate_browser_proof

        with tempfile.TemporaryDirectory() as td:
            artifacts = Path(td)
            self._write_browser_artifact(
                artifacts,
                scenarios=[
                    {
                        "scenario_id": "real-browser-disposable-stack",
                        "status": "passed",
                        "assertions": [{"ok": False, "message": "leak detected"}],
                    },
                    {
                        "scenario_id": "approval-dispatch-worker-kill-switch",
                        "status": "passed",
                        "assertions": [{"ok": True, "message": "worker stopped"}],
                    },
                ],
            )
            with patch(
                "services.payment_recovery.evidence_collector.ARTIFACTS",
                artifacts,
            ):
                ev = evaluate_browser_proof(current_commit="abc")

        self.assertEqual(ev.status, "unverified")
        self.assertEqual(ev.reason, "browser_assertions_invalid")

    def test_collector_verifies_only_correlated_offline_artifacts(self):
        from services.payment_recovery.evidence_collector import collect_competition_evidence

        with tempfile.TemporaryDirectory() as td:
            artifacts = Path(td)
            self._write_backend_artifact(artifacts)
            self._write_browser_artifact(artifacts)
            with patch(
                "services.payment_recovery.evidence_collector.ARTIFACTS",
                artifacts,
            ):
                report = collect_competition_evidence(current_commit="abc")

        self.assertEqual(report["aggregate_status"], "verified_offline")

    def test_collector_rejects_mismatched_evidence_identity(self):
        from services.payment_recovery.evidence_collector import collect_competition_evidence

        with tempfile.TemporaryDirectory() as td:
            artifacts = Path(td)
            self._write_backend_artifact(artifacts)
            self._write_browser_artifact(artifacts, run_id="different-run")
            with patch(
                "services.payment_recovery.evidence_collector.ARTIFACTS",
                artifacts,
            ):
                report = collect_competition_evidence(current_commit="abc")

        self.assertEqual(report["aggregate_status"], "unverified")

    def test_failed_browser_artifact_fails_aggregate(self):
        from services.payment_recovery.evidence_collector import collect_competition_evidence

        with tempfile.TemporaryDirectory() as td:
            artifacts = Path(td)
            self._write_backend_artifact(artifacts)
            self._write_browser_artifact(
                artifacts,
                status="failed",
                dimensions={
                    "backend_invariants": "not_in_this_artifact",
                    "browser_e2e": "failed",
                    "backend_api": "passed",
                    "postgresql": "passed",
                    "redis": "passed",
                    "worker_execution": "passed",
                    "staging_provider": "blocked",
                },
            )
            with patch(
                "services.payment_recovery.evidence_collector.ARTIFACTS",
                artifacts,
            ):
                report = collect_competition_evidence(current_commit="abc")

        self.assertEqual(report["aggregate_status"], "failed")

    def test_collector_never_full_pass_without_browser(self):
        from services.payment_recovery.evidence_collector import collect_competition_evidence

        with tempfile.TemporaryDirectory() as td:
            artifacts = Path(td)
            self._write_backend_artifact(artifacts)
            with patch(
                "services.payment_recovery.evidence_collector.ARTIFACTS",
                artifacts,
            ):
                report = collect_competition_evidence(current_commit="abc")

        self.assertEqual(report["aggregate_status"], "partial_backend_only")
        staging = next(c for c in report["claims"] if c["claim_id"] == "staging_provider")
        self.assertEqual(staging["status"], "blocked")


if __name__ == "__main__":
    unittest.main()

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
        with patch("api.routes_proof._git_commit_sha", return_value="cafebabe"):
            self.assertEqual(_stale_status(data), "commit_mismatch")


class EvidenceCollectorTests(unittest.TestCase):
    def test_missing_browser_is_not_run_not_verified(self):
        from services.payment_recovery.evidence_collector import evaluate_browser_proof

        with patch(
            "services.payment_recovery.evidence_collector.ARTIFACTS",
            Path(tempfile.mkdtemp()),
        ):
            ev = evaluate_browser_proof(current_commit="abc")
        self.assertEqual(ev.status, "not_run")

    def test_collector_never_full_pass_without_browser(self):
        from services.payment_recovery.evidence_collector import collect_competition_evidence

        report = collect_competition_evidence(current_commit="abc123")
        self.assertIn(report["aggregate_status"], {"partial", "partial_backend_only", "failed", "unverified"})
        self.assertNotEqual(report["aggregate_status"], "verified_full")
        staging = next(c for c in report["claims"] if c["claim_id"] == "staging_provider")
        self.assertEqual(staging["status"], "blocked")


if __name__ == "__main__":
    unittest.main()

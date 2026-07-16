"""
P6.4 — Minimal evidence collector.

Reads proof artifacts, validates schema/commit/redaction, computes claim status.
Never writes "verified" without artifacts. Never mutates source artifacts.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.payment_recovery.proof import _git_commit_sha, load_sanitized_artifact

PROOF_SCHEMA = "proof-artifact-v1"
ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "artifacts"


@dataclass
class ClaimEvaluation:
    claim_id: str
    claim: str
    artifact: str
    demo_moment: str
    owner: str
    status: str  # verified|partial|unverified|blocked|not_run|failed
    commit_sha: str | None
    run_id: str | None
    reason: str
    redaction_status: str
    limitations: list[str]


def _read_optional(path: Path) -> tuple[dict[str, Any] | None, str]:
    if not path.is_file():
        return None, "missing_artifact"
    try:
        data = load_sanitized_artifact(path)
        return data, "passed"
    except ValueError:
        return None, "redaction_failed"
    except Exception:
        return None, "read_failed"


def evaluate_backend_proof(current_commit: str | None = None) -> ClaimEvaluation:
    current = current_commit or _git_commit_sha()
    path = ARTIFACTS / "proof-backend-latest.json"
    if not path.is_file():
        path = ARTIFACTS / "proof-backend.json"
    data, redaction = _read_optional(path)
    if data is None:
        return ClaimEvaluation(
            claim_id="proof_backend",
            claim="Backend safety invariants via Proof Mode",
            artifact=str(path.name),
            demo_moment="Run proof suite from admin Proof UI or CLI",
            owner="implementation-owner",
            status="unverified",
            commit_sha=None,
            run_id=None,
            reason=redaction,
            redaction_status=redaction,
            limitations=["No backend proof artifact"],
        )

    art_commit = data.get("commit_sha")
    dims = data.get("dimensions") or {}
    backend = dims.get("backend_invariants") or data.get("status")
    reasons: list[str] = []
    if redaction != "passed":
        reasons.append(redaction)
    if not data.get("schema_version"):
        reasons.append("missing_schema_version")
    elif data.get("schema_version") != PROOF_SCHEMA:
        reasons.append("schema_mismatch")
    if art_commit and current not in ("unknown", None) and art_commit != current:
        reasons.append("commit_mismatch")

    if "commit_mismatch" in reasons or "schema_mismatch" in reasons or "missing_schema_version" in reasons:
        status = "unverified"
    elif backend == "passed" and not reasons:
        status = "verified"
    elif backend == "failed":
        status = "failed"
        reasons.append("backend_failed")
    elif backend == "blocked":
        status = "blocked"
    else:
        status = "partial" if backend else "unverified"

    lim: list[str] = []
    limitations = data.get("limitations")
    if isinstance(limitations, dict):
        lim = [str(v) for v in limitations.values()]

    return ClaimEvaluation(
        claim_id="proof_backend",
        claim="Backend safety invariants via Proof Mode",
        artifact=path.name,
        demo_moment="Admin Proof Mode → run suite seed 42",
        owner="implementation-owner",
        status=status,
        commit_sha=art_commit,
        run_id=data.get("run_id"),
        reason=";".join(reasons) if reasons else "ok",
        redaction_status=redaction,
        limitations=lim,
    )


def evaluate_browser_proof(current_commit: str | None = None) -> ClaimEvaluation:
    current = current_commit or _git_commit_sha()
    path = ARTIFACTS / "proof-browser.json"
    data, redaction = _read_optional(path)
    if data is None:
        return ClaimEvaluation(
            claim_id="proof_browser",
            claim="Browser cache isolation and recovery UI flows",
            artifact="proof-browser.json",
            demo_moment="Playwright P7.1a",
            owner="implementation-owner",
            status="not_run",
            commit_sha=None,
            run_id=None,
            reason="missing_artifact",
            redaction_status=redaction,
            limitations=["Playwright suite required"],
        )
    art_commit = data.get("commit_sha")
    if art_commit and current not in ("unknown", None) and art_commit != current:
        return ClaimEvaluation(
            claim_id="proof_browser",
            claim="Browser cache isolation and recovery UI flows",
            artifact=path.name,
            demo_moment="Playwright P7.1a",
            owner="implementation-owner",
            status="unverified",
            commit_sha=art_commit,
            run_id=data.get("run_id"),
            reason="commit_mismatch",
            redaction_status=redaction,
            limitations=[],
        )
    st = data.get("status") or "unverified"
    return ClaimEvaluation(
        claim_id="proof_browser",
        claim="Browser cache isolation and recovery UI flows",
        artifact=path.name,
        demo_moment="Playwright P7.1a",
        owner="implementation-owner",
        status="verified" if st == "passed" else st,
        commit_sha=art_commit,
        run_id=data.get("run_id"),
        reason="ok" if st == "passed" else st,
        redaction_status=redaction,
        limitations=[],
    )


def collect_competition_evidence(current_commit: str | None = None) -> dict[str, Any]:
    current = current_commit or _git_commit_sha()
    backend = evaluate_backend_proof(current)
    browser = evaluate_browser_proof(current)
    claims = [
        backend,
        browser,
        ClaimEvaluation(
            claim_id="staging_provider",
            claim="Live WhatsApp/payment staging send",
            artifact="docs/staging-gate-p4.7.md",
            demo_moment="Controlled staging recipient",
            owner="operator",
            status="blocked",
            commit_sha=current,
            run_id=None,
            reason="credentials_unavailable",
            redaction_status="n/a",
            limitations=["P4.7 external credentials required"],
        ),
    ]
    aggregate = "partial"
    if backend.status == "verified" and browser.status == "not_run":
        aggregate = "partial_backend_only"
    if backend.status == "failed":
        aggregate = "failed"
    return {
        "schema_version": "competition-evidence-v1",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "commit_sha": current,
        "aggregate_status": aggregate,
        "claims": [asdict(c) for c in claims],
        "rules": {
            "manual_verified_forbidden": True,
            "browser_required_for_full_pass": True,
            "staging_separate_from_simulator": True,
        },
        "disclaimer": (
            "Statuses computed from artifacts only. "
            "Missing browser artifact cannot yield full PASS. "
            "Staging remains blocked without credentials."
        ),
    }


def write_competition_evidence_report(path: Path | None = None) -> Path:
    out = path or (ARTIFACTS / "competition-evidence-status.json")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    report = collect_competition_evidence()
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return out

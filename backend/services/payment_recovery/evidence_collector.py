"""
P6.4 — Minimal evidence collector.

Reads proof artifacts, validates schema/commit/redaction, computes claim status.
Never writes "verified" without artifacts. Never mutates source artifacts.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.payment_recovery.proof import (
    _git_commit_sha,
    git_source_tree_clean,
    load_sanitized_artifact,
)

PROOF_SCHEMA = "proof-artifact-v1"
ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "artifacts"


_BACKEND_ASSERTION_MESSAGES = {
    "duplicate-webhook": (
        "first delivery fact changes dispatch",
        "duplicate delivery fact is a no-op",
        "duplicate has explicit no-transition evidence",
        "duplicate cannot downgrade delivery state",
    ),
    "paid-before-send": (
        "paid order not eligible for send",
        "suppression for non-pending/paid order",
    ),
    "provider-timeout-reconcile": (
        "timeout → provider_unknown",
        "stable message id → accepted",
        "missing message id not accepted",
        "explicit rejection terminal",
        "non-contract unknown",
    ),
    "crash-after-accept": (
        "accepted is durable evidence class",
        "crash mid-flight is unknown not failed_retryable",
        "unknown is not rejection",
    ),
    "redis-loss": (
        "enqueue uses ON CONFLICT durable insert",
        "persists BackgroundJob before async",
        "durable enqueue does not depend on Redis",
        "job ledger is PostgreSQL background_jobs",
    ),
    "cross-tenant": (
        "foreign dispatch is not projected",
        "lookup fails closed",
        "dispatch lookup is tenant and channel scoped",
        "foreign tenant state is untouched",
    ),
    "stale-approval": (
        "production revalidation blocks mutated action",
        "mutation returns approval_stale",
        "revalidation reached current template facts",
    ),
    "consent-withdrawal-stop": (
        "STOP exact",
        "BERHENTI exact",
        "BATAL does not auto opt-out",
        "multi-word not opt-out",
    ),
    "quiet-hours-expiry": (
        "quiet hours defers send",
        "invalid expiry suppresses (None)",
        "empty expiry suppresses",
        "valid expiry parsed aware",
    ),
    "unsafe-ai": (
        "forbidden financial keys rejected",
        "allowlisted variant accepted",
        "static baseline available",
    ),
    "log-redaction": (
        "no access_token field",
        "no bearer token",
        "phone masked",
    ),
    "legacy-scheduler-off": (
        "SCHEDULER_ENABLED default false",
        "legacy followup default false",
        "payment recovery default false",
        "recovery mode default observe",
        "proof mode default false",
    ),
}
_BACKEND_PROVIDER_CALLS = {
    scenario_id: 1 if scenario_id in {
        "provider-timeout-reconcile",
        "crash-after-accept",
    } else 0
    for scenario_id in _BACKEND_ASSERTION_MESSAGES
}
_BROWSER_ASSERTION_MESSAGES = {
    "real-browser-disposable-stack": (
        "Playwright passed: real auth tenant switch clears A before B",
        "Playwright passed: real public capability exchange establishes an HttpOnly session",
        "Playwright passed: real approval creates a durable dispatch",
    ),
    "approval-dispatch-worker-kill-switch": (
        "real approval created a durable PostgreSQL dispatch and job",
        "real worker claim stopped before provider at the global kill switch",
    ),
}


_BACKEND_ALLOWED_FIELDS = frozenset({
    "run_id", "suite", "seed", "schema_version", "redaction_status",
    "commit_sha", "source_tree_clean", "started_at", "finished_at",
    "command", "environment", "scenarios", "required_backend_scenarios",
    "missing_required", "empty_assertion_failures", "summary", "dimensions",
    "status", "disclaimer", "watermark", "actor_user_id", "generated_at",
    "limitations", "verification_status", "unverified_reason",
})
_BROWSER_ALLOWED_FIELDS = frozenset({
    "schema_version", "suite", "run_id", "seed", "commit_sha",
    "source_tree_clean", "status", "started_at", "finished_at", "command",
    "environment", "watermark", "redaction_status", "api_mocking",
    "dimensions", "scenarios", "summary", "infrastructure", "disclaimer",
    "verification_status", "unverified_reason",
})


_BACKEND_SCENARIO_DIGESTS = {
    "duplicate-webhook": "07c3acc3dae1c8c7cf11c05b1783eae8f3e7586f72128a767d20d71bdf69392c",
    "paid-before-send": "48374a2780c946abb5f9a205c1ca5bed0016b610f4ddc4a4b8ad66619be4f1e0",
    "provider-timeout-reconcile": "f08265b9e64020b28bbf3e910814a2239172e643c9fcf279605c4bf1b990405a",
    "crash-after-accept": "947c6c83c72f2c53a91769fef52a426476b2c746c6cd289dcf2b63224aa23bd9",
    "redis-loss": "68bff2921684230e28b3bdc17dc20a3ce7f3286dc55a75e3a3952e81c3cb843d",
    "cross-tenant": "89fa9657e9069876215d043343aacb72d9ffdf89923236f6cf18e83625174093",
    "stale-approval": "ea4c65781bd4d69d1f778be1fd18e4247f23c420dc29d25b5ecbae376628a310",
    "consent-withdrawal-stop": "bae4384fff2541096aba31ed27eb0702467f3b622cc8f44b91aa5c274d66a87d",
    "quiet-hours-expiry": "beba97487737680c9b32dfcf7ca153852b5b0657ec98f2d5b600c65f5442a02d",
    "unsafe-ai": "3c7082ca9e8b971f755d77c684e4b7785c5824147fcca929114f3ca3115d47fd",
    "log-redaction": "fdc4e644414e4b40e0d5dd7d4caaab93c3bfd3f39cd9d1eb70de6dbd3be08b87",
    "legacy-scheduler-off": "32107a158d01e64ffd68d08308d91dea88a159f685aeb56d19ec60769121bac4",
}


def _scenario_digest(scenario: dict[str, Any]) -> str:
    encoded = json.dumps(
        scenario,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


_BROWSER_ASSERTIONS = {
    "real-browser-disposable-stack": [
        {
            "ok": True,
            "message": message,
            "audit_code": "real_browser_runtime",
        }
        for message in _BROWSER_ASSERTION_MESSAGES["real-browser-disposable-stack"]
    ],
    "approval-dispatch-worker-kill-switch": [
        {
            "ok": True,
            "message": _BROWSER_ASSERTION_MESSAGES[
                "approval-dispatch-worker-kill-switch"
            ][0],
            "audit_code": "approval_to_dispatch_real_db",
        },
        {
            "ok": True,
            "message": _BROWSER_ASSERTION_MESSAGES[
                "approval-dispatch-worker-kill-switch"
            ][1],
            "audit_code": "worker_pre_send_revalidation",
        },
    ],
}


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
    seed: int | None = None


def _read_optional(path: Path) -> tuple[dict[str, Any] | None, str]:
    if not path.is_file():
        return None, "missing_artifact"
    try:
        data = load_sanitized_artifact(path)
        return data, "passed"
    except json.JSONDecodeError:
        return None, "read_failed"
    except ValueError:
        return None, "redaction_failed"
    except Exception:
        return None, "read_failed"


def _valid_time_window(data: dict[str, Any]) -> bool:
    parsed: list[datetime] = []
    for key in ("started_at", "finished_at"):
        raw = data.get(key)
        if not isinstance(raw, str) or not raw.strip():
            return False
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return False
        if value.tzinfo is None or value.utcoffset() is None:
            return False
        parsed.append(value)
    return parsed[1] >= parsed[0]


def artifact_metadata_verification_error(
    data: dict[str, Any], *, expected_suite: str
) -> str | None:
    """Validate metadata required for every artifact status, not only passes."""
    if data.get("source_tree_clean") is not True:
        return "source_tree_dirty"
    if not _valid_time_window(data):
        return "invalid_time_window"
    run_id = data.get("run_id")
    seed = data.get("seed")
    if (
        not isinstance(run_id, str)
        or not run_id.strip()
        or isinstance(seed, bool)
        or not isinstance(seed, int)
    ):
        return f"{expected_suite}_identity_missing"
    if not isinstance(data.get("dimensions"), dict):
        return f"{expected_suite}_metadata_invalid"
    if not isinstance(data.get("scenarios"), list):
        return f"{expected_suite}_metadata_invalid"
    if not isinstance(data.get("summary"), dict):
        return f"{expected_suite}_metadata_invalid"
    environment = str(data.get("environment") or "").strip().lower()
    if environment not in {"local", "test", "ci", "local_disposable"}:
        return f"{expected_suite}_environment_invalid"
    return None


def artifact_structure_verification_error(
    data: dict[str, Any], *, expected_suite: str
) -> str | None:
    """Validate status/dimension/scenario/summary consistency for all outcomes."""
    status = data.get("status")
    dimensions = data.get("dimensions")
    scenarios = data.get("scenarios")
    summary = data.get("summary")
    if not isinstance(dimensions, dict) or not isinstance(scenarios, list):
        return f"{expected_suite}_metadata_invalid"

    dimension_name = "backend_invariants" if expected_suite == "backend" else "browser_e2e"
    dimension_status = dimensions.get(dimension_name)
    if status in {"passed", "failed", "blocked", "not_run"}:
        expected_dimension = "not_run" if status == "not_run" else status
        if dimension_status != expected_dimension:
            return f"{expected_suite}_status_dimension_mismatch"
    elif status in {"unverified", "UNVERIFIED"} and dimension_status == "passed":
        return f"{expected_suite}_status_dimension_mismatch"

    if expected_suite == "backend":
        from services.payment_recovery.proof import (
            BROWSER_SCENARIO_ID,
            REQUIRED_BACKEND_SCENARIOS,
        )

        if set(dimensions) != {
            "backend_invariants",
            "browser_e2e",
            "staging_provider",
        }:
            return "backend_metadata_invalid"
        scenario_ids = [
            scenario.get("scenario_id") if isinstance(scenario, dict) else None
            for scenario in scenarios
        ]
        expected_ids = set(REQUIRED_BACKEND_SCENARIOS) | {BROWSER_SCENARIO_ID}
        if len(scenario_ids) != len(set(scenario_ids)) or set(scenario_ids) != expected_ids:
            return "backend_assertions_invalid"
        counts = {
            outcome: sum(
                1
                for scenario in scenarios
                if isinstance(scenario, dict) and scenario.get("status") == outcome
            )
            for outcome in (
                "passed",
                "failed",
                "blocked",
                "skipped",
                "not_run",
                "unverified",
            )
        }
        expected_summary = {
            "total": len(scenarios),
            **counts,
            "backend_required": len(REQUIRED_BACKEND_SCENARIOS),
            "backend_passed": counts["passed"],
        }
        if summary != expected_summary:
            return "backend_summary_invalid"
    else:
        if data.get("api_mocking") is False:
            scenario_ids = [
                scenario.get("scenario_id") if isinstance(scenario, dict) else None
                for scenario in scenarios
            ]
            if len(scenario_ids) != len(set(scenario_ids)) or set(scenario_ids) != set(
                _BROWSER_ASSERTION_MESSAGES
            ):
                return "browser_assertions_invalid"
        assertion_items = [
            assertion
            for scenario in scenarios
            if isinstance(scenario, dict)
            for assertion in (
                scenario.get("assertions")
                if isinstance(scenario.get("assertions"), list)
                else []
            )
        ]
        expected_summary = {
            "total": len(assertion_items),
            "passed": sum(
                1
                for assertion in assertion_items
                if isinstance(assertion, dict) and assertion.get("ok") is True
            ),
            "failed": sum(
                1
                for assertion in assertion_items
                if not isinstance(assertion, dict) or assertion.get("ok") is not True
            ),
        }
        if summary != expected_summary:
            return "browser_summary_invalid"
    return None


def backend_pass_verification_error(data: dict[str, Any]) -> str | None:
    """Return why a claimed backend pass lacks complete assertion evidence."""
    from services.payment_recovery.proof import (
        BROWSER_SCENARIO_ID,
        REQUIRED_BACKEND_SCENARIOS,
    )

    if not set(data).issubset(_BACKEND_ALLOWED_FIELDS):
        return "backend_schema_invalid"
    if data.get("redaction_status") != "passed":
        return "artifact_redaction_unverified"
    if data.get("source_tree_clean") is not True:
        return "source_tree_dirty"
    if not _valid_time_window(data):
        return "invalid_time_window"

    run_id = data.get("run_id")
    seed = data.get("seed")
    if (
        not isinstance(run_id, str)
        or not run_id.strip()
        or isinstance(seed, bool)
        or not isinstance(seed, int)
    ):
        return "backend_identity_missing"

    dimensions = data.get("dimensions")
    expected_dimensions = {
        "backend_invariants": "passed",
        "browser_e2e": "not_run",
        "staging_provider": "blocked",
    }
    if (
        data.get("suite") != "backend"
        or data.get("status") != "passed"
        or dimensions != expected_dimensions
        or data.get("required_backend_scenarios") != list(REQUIRED_BACKEND_SCENARIOS)
        or data.get("missing_required") != []
        or data.get("empty_assertion_failures") != []
        or data.get("command")
        != f"python -m scripts.proof_mode run-all --suite backend --seed {seed}"
        or data.get("disclaimer")
        != (
            "Offline deterministic proof of safety invariants. "
            "Does not prove live WhatsApp/payment staging. "
            "Browser scenario remains not_run until Playwright produces proof-browser.json."
        )
    ):
        return "backend_assertions_invalid"

    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list):
        return "backend_assertions_invalid"
    by_id: dict[str, dict[str, Any]] = {}
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            return "backend_assertions_invalid"
        scenario_id = scenario.get("scenario_id")
        provider_calls = scenario.get("provider_calls")
        if (
            not isinstance(scenario_id, str)
            or scenario_id in by_id
            or isinstance(provider_calls, bool)
            or not isinstance(provider_calls, int)
            or provider_calls < 0
        ):
            return "backend_assertions_invalid"
        by_id[scenario_id] = scenario

    expected_ids = set(REQUIRED_BACKEND_SCENARIOS) | {BROWSER_SCENARIO_ID}
    if set(by_id) != expected_ids:
        return "backend_assertions_invalid"
    for scenario_id in REQUIRED_BACKEND_SCENARIOS:
        scenario = by_id[scenario_id]
        assertions = scenario.get("assertions")
        if (
            scenario.get("status") != "passed"
            or scenario.get("seed") != seed
            or scenario.get("provider_calls") != _BACKEND_PROVIDER_CALLS[scenario_id]
            or not isinstance(assertions, list)
            or not assertions
            or any(
                not isinstance(assertion, dict)
                or assertion.get("ok") is not True
                or not isinstance(assertion.get("message"), str)
                or not assertion.get("message").strip()
                for assertion in assertions
            )
        ):
            return "backend_assertions_invalid"
        if tuple(assertion["message"] for assertion in assertions) != (
            _BACKEND_ASSERTION_MESSAGES[scenario_id]
        ):
            return "backend_assertions_invalid"
        if _scenario_digest(scenario) != _BACKEND_SCENARIO_DIGESTS[scenario_id]:
            return "backend_assertions_invalid"

    browser = by_id[BROWSER_SCENARIO_ID]
    if (
        browser.get("status") != "not_run"
        or browser.get("seed") != seed
        or browser.get("assertions") != []
        or browser.get("provider_calls") != 0
    ):
        return "backend_assertions_invalid"

    counts = {
        status: sum(
            1 for scenario in scenarios if scenario.get("status") == status
        )
        for status in ("passed", "failed", "blocked", "skipped", "not_run", "unverified")
    }
    expected_summary = {
        "total": len(scenarios),
        **counts,
        "backend_required": len(REQUIRED_BACKEND_SCENARIOS),
        "backend_passed": len(REQUIRED_BACKEND_SCENARIOS),
    }
    if data.get("summary") != expected_summary:
        return "backend_summary_invalid"
    return None


def evaluate_backend_proof(
    current_commit: str | None = None,
    current_tree_clean: bool | None = None,
) -> ClaimEvaluation:
    current = current_commit or _git_commit_sha()
    tree_clean = (
        git_source_tree_clean()
        if current_tree_clean is None
        else current_tree_clean
    )
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
            limitations=["No valid backend proof artifact"],
        )

    art_commit = data.get("commit_sha")
    run_id = data.get("run_id")
    seed = data.get("seed")
    dimensions = data.get("dimensions")
    backend_status = (
        dimensions.get("backend_invariants")
        if isinstance(dimensions, dict)
        else data.get("status")
    )
    reasons: list[str] = []
    if not tree_clean:
        reasons.append("current_source_tree_dirty")
    metadata_error = artifact_metadata_verification_error(
        data, expected_suite="backend"
    )
    if metadata_error:
        reasons.append(metadata_error)
    structure_error = artifact_structure_verification_error(
        data, expected_suite="backend"
    )
    if structure_error and structure_error not in reasons:
        reasons.append(structure_error)
    if data.get("status") not in {
        "passed",
        "failed",
        "blocked",
        "not_run",
        "unverified",
        "UNVERIFIED",
    }:
        reasons.append("backend_status_invalid")
    if backend_status not in {"passed", "failed", "blocked", "unverified"}:
        reasons.append("backend_status_invalid")
    if redaction != "passed":
        reasons.append(redaction)
    if not data.get("schema_version"):
        reasons.append("missing_schema_version")
    elif data.get("schema_version") != PROOF_SCHEMA:
        reasons.append("schema_mismatch")
    if not isinstance(art_commit, str) or not art_commit.strip():
        reasons.append("missing_commit_identity")
    elif current in ("unknown", None):
        reasons.append("current_commit_unknown")
    elif art_commit != current:
        reasons.append("commit_mismatch")
    if (
        not isinstance(run_id, str)
        or not run_id.strip()
        or isinstance(seed, bool)
        or not isinstance(seed, int)
    ):
        reasons.append("missing_evidence_identity")
    if backend_status == "passed":
        payload_error = backend_pass_verification_error(data)
        if payload_error and payload_error not in reasons:
            reasons.append(payload_error)

    verification_errors = {
        "commit_mismatch",
        "schema_mismatch",
        "missing_schema_version",
        "missing_commit_identity",
        "current_commit_unknown",
        "missing_evidence_identity",
        "redaction_failed",
        "read_failed",
        "backend_assertions_invalid",
        "backend_summary_invalid",
        "artifact_redaction_unverified",
        "invalid_time_window",
        "source_tree_dirty",
        "current_source_tree_dirty",
        "backend_identity_missing",
        "backend_metadata_invalid",
        "backend_environment_invalid",
        "backend_status_invalid",
        "backend_schema_invalid",
        "backend_status_dimension_mismatch",
    }
    if verification_errors.intersection(reasons):
        status = "unverified"
    elif backend_status == "passed" and not reasons:
        status = "verified"
    elif backend_status == "failed":
        status = "failed"
        reasons.append("backend_failed")
    elif backend_status == "blocked":
        status = "blocked"
    else:
        status = "partial" if backend_status else "unverified"

    limitations: list[str] = []
    artifact_limitations = data.get("limitations")
    if isinstance(artifact_limitations, dict):
        limitations = [str(value) for value in artifact_limitations.values()]

    return ClaimEvaluation(
        claim_id="proof_backend",
        claim="Backend safety invariants via Proof Mode",
        artifact=path.name,
        demo_moment="Admin Proof Mode → run suite seed 42",
        owner="implementation-owner",
        status=status,
        commit_sha=art_commit,
        run_id=run_id,
        reason=";".join(reasons) if reasons else "ok",
        redaction_status=redaction,
        limitations=limitations,
        seed=seed if isinstance(seed, int) and not isinstance(seed, bool) else None,
    )


def browser_pass_verification_error(data: dict[str, Any]) -> str | None:
    """Return why a claimed browser pass is not release-grade evidence."""
    if not set(data).issubset(_BROWSER_ALLOWED_FIELDS):
        return "browser_schema_mismatch"
    if data.get("source_tree_clean") is not True:
        return "source_tree_dirty"
    if not _valid_time_window(data):
        return "invalid_time_window"

    dimensions = data.get("dimensions")
    if not isinstance(dimensions, dict):
        return "browser_metadata_invalid"
    disclaimer = str(data.get("disclaimer") or "")
    browser_dimension = str(dimensions.get("browser_e2e") or "")
    if (
        data.get("api_mocking") is True
        or "mocked" in browser_dimension.lower()
        or "mocked" in disclaimer.lower()
    ):
        return "mocked_browser_artifact"
    if data.get("schema_version") != PROOF_SCHEMA:
        return "browser_schema_mismatch"
    if data.get("suite") != "browser":
        return "browser_suite_mismatch"
    if data.get("redaction_status") != "passed":
        return "browser_redaction_unverified"
    if data.get("api_mocking") is not False:
        return "browser_stack_unproven"
    if any(
        not isinstance(data.get(name), str) or not data.get(name).strip()
        for name in ("commit_sha", "run_id", "started_at", "finished_at")
    ) or isinstance(data.get("seed"), bool) or not isinstance(data.get("seed"), int):
        return "browser_identity_missing"

    expected_dimensions = {
        "backend_invariants": "not_in_this_artifact",
        "browser_e2e": "passed",
        "backend_api": "passed",
        "postgresql": "passed",
        "redis": "passed",
        "worker_execution": "passed",
        "staging_provider": "blocked",
    }
    expected_infrastructure = {
        "loopback_only": True,
        "postgresql": "guarded_disposable_tmpfs",
        "redis": "guarded_disposable_no_persistence",
        "migration_rehearsal": "20260717_0012_downgrade_reupgrade_passed",
    }
    expected_disclaimer = (
        "Focused real local browser/backend/PostgreSQL/Redis proof with synthetic data. "
        "No live payment or messaging provider was called. DATA SIMULASI."
    )
    if (
        dimensions != expected_dimensions
        or data.get("infrastructure") != expected_infrastructure
        or data.get("command") != "python -m scripts.run_disposable_browser_e2e"
        or data.get("environment") not in {"ci", "local_disposable"}
        or disclaimer != expected_disclaimer
    ):
        return "browser_stack_unproven"

    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return "browser_assertions_invalid"
    expected_scenarios = {
        "real-browser-disposable-stack",
        "approval-dispatch-worker-kill-switch",
    }
    scenario_ids = [
        scenario.get("scenario_id") if isinstance(scenario, dict) else None
        for scenario in scenarios
    ]
    if len(scenario_ids) != len(set(scenario_ids)) or set(scenario_ids) != expected_scenarios:
        return "browser_assertions_invalid"

    assertion_count = 0
    for scenario in scenarios:
        if scenario.get("status") != "passed" or scenario.get("provider_calls") != 0:
            return "browser_assertions_invalid"
        assertions = scenario.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            return "browser_assertions_invalid"
        if any(
            not isinstance(item, dict)
            or item.get("ok") is not True
            or not isinstance(item.get("message"), str)
            or not item.get("message").strip()
            for item in assertions
        ):
            return "browser_assertions_invalid"
        expected_messages = _BROWSER_ASSERTION_MESSAGES[scenario["scenario_id"]]
        if tuple(item["message"] for item in assertions) != expected_messages:
            return "browser_assertions_invalid"
        if assertions != _BROWSER_ASSERTIONS[scenario["scenario_id"]]:
            return "browser_assertions_invalid"
        assertion_count += len(assertions)

    summary = data.get("summary")
    if not isinstance(summary, dict) or summary != {
        "total": assertion_count,
        "passed": assertion_count,
        "failed": 0,
    }:
        return "browser_summary_invalid"
    return None


def evaluate_browser_proof(
    current_commit: str | None = None,
    current_tree_clean: bool | None = None,
) -> ClaimEvaluation:
    current = current_commit or _git_commit_sha()
    tree_clean = (
        git_source_tree_clean()
        if current_tree_clean is None
        else current_tree_clean
    )
    path = ARTIFACTS / "proof-browser.json"
    data, redaction = _read_optional(path)
    if data is None:
        artifact_missing = redaction == "missing_artifact"
        return ClaimEvaluation(
            claim_id="proof_browser",
            claim="Disposable-stack browser cache, capability, and recovery approval flows",
            artifact="proof-browser.json",
            demo_moment="Focused real Playwright disposable-stack suite",
            owner="implementation-owner",
            status="not_run" if artifact_missing else "unverified",
            commit_sha=None,
            run_id=None,
            reason=redaction,
            redaction_status=redaction,
            limitations=[
                "Playwright suite required"
                if artifact_missing
                else "Browser artifact could not be verified"
            ],
        )

    art_commit = data.get("commit_sha")
    run_id = data.get("run_id")
    seed = data.get("seed")
    dimensions = data.get("dimensions")
    generic_metadata_error = artifact_metadata_verification_error(
        data, expected_suite="browser"
    )
    structure_error = (
        artifact_structure_verification_error(data, expected_suite="browser")
        if data.get("status") != "passed"
        else None
    )
    metadata_error: str | None = None
    if data.get("schema_version") != PROOF_SCHEMA:
        metadata_error = "browser_schema_mismatch"
    elif data.get("suite") != "browser":
        metadata_error = "browser_suite_mismatch"
    elif data.get("redaction_status") != "passed":
        metadata_error = "browser_redaction_unverified"
    elif generic_metadata_error:
        metadata_error = generic_metadata_error
    elif structure_error:
        metadata_error = structure_error
    elif not isinstance(dimensions, dict):
        metadata_error = "browser_metadata_invalid"
    elif (
        not isinstance(art_commit, str)
        or not art_commit.strip()
        or not isinstance(run_id, str)
        or not run_id.strip()
        or isinstance(seed, bool)
        or not isinstance(seed, int)
    ):
        metadata_error = "browser_identity_missing"
    elif current in ("unknown", None):
        metadata_error = "current_commit_unknown"
    elif not tree_clean:
        metadata_error = "current_source_tree_dirty"
    elif art_commit != current:
        metadata_error = "commit_mismatch"

    artifact_status = data.get("status") or "unverified"
    if metadata_error:
        status = "unverified"
        reason = metadata_error
    elif artifact_status == "passed":
        reason = browser_pass_verification_error(data) or "ok"
        status = "verified" if reason == "ok" else "unverified"
    elif artifact_status in {"failed", "blocked", "not_run", "unverified"}:
        status = artifact_status
        reason = str(artifact_status)
    else:
        status = "unverified"
        reason = "browser_status_invalid"

    return ClaimEvaluation(
        claim_id="proof_browser",
        claim="Disposable-stack browser cache, capability, and recovery approval flows",
        artifact=path.name,
        demo_moment="Focused real Playwright disposable-stack suite",
        owner="implementation-owner",
        status=status,
        commit_sha=art_commit,
        run_id=run_id,
        reason=reason,
        redaction_status=redaction,
        limitations=[] if status == "verified" else ["Real backend/PostgreSQL/Redis browser proof required"],
        seed=seed if isinstance(seed, int) and not isinstance(seed, bool) else None,
    )


def collect_competition_evidence(current_commit: str | None = None) -> dict[str, Any]:
    current = current_commit or _git_commit_sha()
    current_tree_clean = git_source_tree_clean()
    backend = evaluate_backend_proof(current, current_tree_clean)
    browser = evaluate_browser_proof(current, current_tree_clean)
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

    if "failed" in {backend.status, browser.status}:
        aggregate = "failed"
    elif backend.status == "verified" and browser.status == "verified":
        identities_match = (
            backend.commit_sha == browser.commit_sha == current
            and bool(backend.run_id)
            and backend.run_id == browser.run_id
            and backend.seed is not None
            and backend.seed == browser.seed
        )
        aggregate = "verified_offline" if identities_match else "unverified"
    elif backend.status == "verified" and browser.status == "not_run":
        aggregate = "partial_backend_only"
    elif "unverified" in {backend.status, browser.status}:
        aggregate = "unverified"
    else:
        aggregate = "partial"

    return {
        "schema_version": "competition-evidence-v1",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "commit_sha": current,
        "aggregate_status": aggregate,
        "claims": [asdict(c) for c in claims],
        "rules": {
            "manual_verified_forbidden": True,
            "browser_required_for_offline_verification": True,
            "exact_commit_run_id_seed_required": True,
            "staging_separate_from_simulator": True,
        },
        "disclaimer": (
            "Statuses computed from artifacts only. "
            "Verified offline evidence is not live-provider or production approval. "
            "Staging remains blocked without credentials."
        ),
    }


def write_competition_evidence_report(path: Path | None = None) -> Path:
    out = path or (ARTIFACTS / "competition-evidence-status.json")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    report = collect_competition_evidence()
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return out

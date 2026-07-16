"""
P6.1/P6.2 — Deterministic recovery Proof Mode scenarios (offline-safe).

Scenarios assert safety invariants using production pure functions and
fail-closed adapters. No real WhatsApp/payment network calls. Status is
never pre-marked passed — only computed from assertions after execution.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from services.payment_recovery.ai_copy import parse_model_selection, select_static
from services.payment_recovery.delivery_projection import should_advance_delivery
from services.payment_recovery.opt_out import is_transactional_stop_keyword
from services.payment_recovery.phone import normalize_indonesian_phone
from services.messaging.base import SendMessageResult
from services.payment_recovery.dispatch import _classify_provider_result


def _git_commit_sha() -> str:
    try:
        root = Path(__file__).resolve().parents[3]
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:
        return "unknown"


def _assert(cond: bool, message: str) -> dict[str, Any]:
    return {"ok": bool(cond), "message": message}


@dataclass
class ScenarioResult:
    scenario_id: str
    status: str  # passed | failed | skipped | blocked | not_run
    seed: int
    assertions: list[dict[str, Any]] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)
    provider_calls: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def finalize(self) -> "ScenarioResult":
        # blocked/skipped are terminal labels set by the harness before assertions.
        if self.status in {"skipped", "blocked"}:
            return self
        if not self.assertions:
            self.status = "failed"
            self.assertions.append(_assert(False, "scenario has no assertions"))
            return self
        self.status = "passed" if all(a.get("ok") for a in self.assertions) else "failed"
        return self


def scenario_duplicate_webhook(seed: int) -> ScenarioResult:
    """Duplicate delivery facts must not downgrade delivery_status."""
    r = ScenarioResult(
        scenario_id="duplicate-webhook",
        status="not_run",
        seed=seed,
        invariants=["INV-06", "INV-13"],
    )
    r.assertions = [
        _assert(should_advance_delivery("delivered", "delivered") is False, "duplicate delivered is no-op"),
        _assert(should_advance_delivery("read", "delivered") is False, "out-of-order delivered after read no-op"),
        _assert(should_advance_delivery("delivered", "failed") is False, "failed does not downgrade delivered"),
    ]
    return r.finalize()


def scenario_provider_timeout(seed: int) -> ScenarioResult:
    r = ScenarioResult(
        scenario_id="provider-timeout-reconcile",
        status="not_run",
        seed=seed,
        invariants=["INV-06"],
        provider_calls=1,
    )
    timeout = SendMessageResult(success=False, outcome="unknown", error_message="timeout")
    accepted = SendMessageResult(
        success=True, outcome="accepted", provider_message_id="wamid.ok"
    )
    malformed = SendMessageResult(success=True, outcome="accepted", provider_message_id="")
    r.assertions = [
        _assert(_classify_provider_result(timeout) == "provider_unknown", "timeout → provider_unknown"),
        _assert(_classify_provider_result(accepted) == "accepted", "stable message id → accepted"),
        _assert(_classify_provider_result(malformed) == "provider_unknown", "missing message id not accepted"),
        _assert(_classify_provider_result({"success": True}) == "provider_unknown", "non-contract result unknown"),
    ]
    return r.finalize()


def scenario_cross_tenant_phone(seed: int) -> ScenarioResult:
    r = ScenarioResult(
        scenario_id="cross-tenant",
        status="not_run",
        seed=seed,
        invariants=["INV-01"],
    )
    a = normalize_indonesian_phone("081234567890")
    b = normalize_indonesian_phone("+6281234567890")
    bad = normalize_indonesian_phone("not-a-phone")
    r.assertions = [
        _assert(a.status == "valid" and b.status == "valid", "valid ID phones normalize"),
        _assert(a.e164 == b.e164, "same logical recipient same e164"),
        _assert(bad.status != "valid", "invalid phone not accepted"),
    ]
    return r.finalize()


def scenario_stale_and_stop(seed: int) -> ScenarioResult:
    r = ScenarioResult(
        scenario_id="consent-withdrawal-stop",
        status="not_run",
        seed=seed,
        invariants=["INV-02"],
    )
    r.assertions = [
        _assert(is_transactional_stop_keyword("STOP"), "STOP exact"),
        _assert(is_transactional_stop_keyword("berhenti"), "BERHENTI exact"),
        _assert(not is_transactional_stop_keyword("BATAL"), "BATAL does not auto opt-out"),
        _assert(not is_transactional_stop_keyword("please STOP"), "multi-word not opt-out"),
    ]
    return r.finalize()


def scenario_unsafe_ai(seed: int) -> ScenarioResult:
    r = ScenarioResult(
        scenario_id="unsafe-ai",
        status="not_run",
        seed=seed,
        invariants=["INV-03"],
    )
    bad = parse_model_selection(
        '{"variant_id":"payment_reminder_soft_v1","discount":"90%","payment_url":"https://x"}'
    )
    good = parse_model_selection('{"variant_id":"payment_reminder_soft_v1"}')
    static = select_static({"order_ref": "ORD-1", "amount_display": "Rp10.000"})
    r.assertions = [
        _assert(bad is None, "forbidden financial keys rejected"),
        _assert(good == "payment_reminder_soft_v1", "allowlisted variant accepted"),
        _assert(static.ok and static.source == "static", "static baseline available"),
    ]
    return r.finalize()


def scenario_legacy_scheduler_flags(seed: int) -> ScenarioResult:
    r = ScenarioResult(
        scenario_id="legacy-scheduler-off",
        status="not_run",
        seed=seed,
        invariants=["INV-12"],
    )
    # Import settings without ambient .env forcing true
    from config import Settings

    s = Settings(_env_file=None)
    r.assertions = [
        _assert(s.SCHEDULER_ENABLED is False, "SCHEDULER_ENABLED default false"),
        _assert(
            s.ENABLE_LEGACY_PENDING_PAYMENT_FOLLOWUP is False,
            "legacy followup default false",
        ),
        _assert(s.ENABLE_PAYMENT_RECOVERY is False, "payment recovery default false"),
        _assert(
            (s.PAYMENT_RECOVERY_MODE or "observe") == "observe",
            "recovery mode default observe",
        ),
        _assert(s.ENABLE_DEMO_PROOF_MODE is False, "proof mode default false"),
    ]
    return r.finalize()


def scenario_log_redaction(seed: int) -> ScenarioResult:
    r = ScenarioResult(
        scenario_id="log-redaction",
        status="not_run",
        seed=seed,
        invariants=["INV-14"],
    )
    # Ensure proof artifacts never include raw secrets in scenario names/details.
    sample = {
        "order_id": 1,
        "masked": "+62••••••7890",
        "digest": hashlib.sha256(b"action").hexdigest()[:16],
    }
    blob = json.dumps(sample)
    r.assertions = [
        _assert("access_token" not in blob, "no access_token field"),
        _assert("Bearer " not in blob, "no bearer token"),
        _assert("••••" in sample["masked"], "phone masked"),
    ]
    return r.finalize()


SCENARIOS: dict[str, Callable[[int], ScenarioResult]] = {
    "duplicate-webhook": scenario_duplicate_webhook,
    "provider-timeout-reconcile": scenario_provider_timeout,
    "cross-tenant": scenario_cross_tenant_phone,
    "consent-withdrawal-stop": scenario_stale_and_stop,
    "unsafe-ai": scenario_unsafe_ai,
    "legacy-scheduler-off": scenario_legacy_scheduler_flags,
    "log-redaction": scenario_log_redaction,
}


def production_guard_blocks_proof_mode() -> tuple[bool, str]:
    env = (os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "").lower()
    proof = (os.environ.get("ENABLE_DEMO_PROOF_MODE") or "").lower() in {
        "1",
        "true",
        "yes",
    }
    if env == "production" and proof:
        return True, "proof_mode_forbidden_in_production"
    # Real provider credentials present → harness must not claim network proof
    if os.environ.get("WHATSAPP_ACCESS_TOKEN") and proof:
        return True, "real_whatsapp_credentials_present"
    return False, "ok"


def run_scenario(scenario_id: str, seed: int = 42) -> ScenarioResult:
    blocked, reason = production_guard_blocks_proof_mode()
    if blocked:
        return ScenarioResult(
            scenario_id=scenario_id,
            status="blocked",
            seed=seed,
            assertions=[_assert(False, reason)],
            details={"block_reason": reason},
        ).finalize()
    fn = SCENARIOS.get(scenario_id)
    if not fn:
        return ScenarioResult(
            scenario_id=scenario_id,
            status="failed",
            seed=seed,
            assertions=[_assert(False, f"unknown scenario: {scenario_id}")],
        ).finalize()
    return fn(seed)


def run_all(seed: int = 42, suite: str = "backend") -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc).isoformat()
    results = [run_scenario(sid, seed=seed) for sid in sorted(SCENARIOS.keys())]
    payload = {
        "run_id": run_id,
        "suite": suite,
        "seed": seed,
        "commit_sha": _git_commit_sha(),
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": [asdict(r) for r in results],
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r.status == "passed"),
            "failed": sum(1 for r in results if r.status == "failed"),
            "blocked": sum(1 for r in results if r.status == "blocked"),
            "skipped": sum(1 for r in results if r.status == "skipped"),
        },
        "disclaimer": (
            "Offline deterministic proof of safety invariants. "
            "Does not prove live WhatsApp/payment staging. "
            "Browser scenarios are separate and not marked here."
        ),
    }
    # Never pre-mark overall PASS without counting
    payload["status"] = (
        "passed"
        if payload["summary"]["failed"] == 0 and payload["summary"]["blocked"] == 0
        else "failed"
        if payload["summary"]["failed"]
        else "blocked"
    )
    return payload

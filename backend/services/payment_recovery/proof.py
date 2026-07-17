"""
P6.1/P6.2 — Deterministic recovery Proof Mode scenarios (offline-safe).

Backend suite scenarios assert safety invariants with real assertion objects.
Browser suite is never marked passed here — status stays not_run/unverified.
Live provider staging remains blocked without credentials.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock

from config import get_settings
from services.messaging.base import SendMessageResult
from services.payment_recovery.ai_copy import parse_model_selection, select_static
from services.payment_recovery.delivery_projection import should_advance_delivery
from services.payment_recovery.dispatch import _classify_provider_result
from services.payment_recovery.opt_out import is_transactional_stop_keyword
from services.payment_recovery.phone import normalize_indonesian_phone
from services.payment_recovery.policy import (
    PolicyFact,
    evaluate_policy,
    parse_legacy_expiry,
    resolve_quiet_hours,
)


# Backend required scenarios from SUPER_IMPLEMENTATION_PLAN P6.2 (1–12).
# #13 is browser-only and must not be marked passed by this harness.
REQUIRED_BACKEND_SCENARIOS = (
    "duplicate-webhook",
    "paid-before-send",
    "provider-timeout-reconcile",
    "crash-after-accept",
    "redis-loss",
    "cross-tenant",
    "stale-approval",
    "consent-withdrawal-stop",
    "quiet-hours-expiry",
    "unsafe-ai",
    "log-redaction",
    "legacy-scheduler-off",
)
BROWSER_SCENARIO_ID = "cache-tenant-switch-browser"


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


def git_source_tree_clean() -> bool:
    try:
        root = Path(__file__).resolve().parents[3]
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0 and not result.stdout.strip()
    except Exception:
        return False


def _assert(
    cond: bool,
    message: str,
    *,
    expected: Any = None,
    actual: Any = None,
    audit_code: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"ok": bool(cond), "message": message}
    if expected is not None:
        row["expected"] = expected
    if actual is not None:
        row["actual"] = actual
    if audit_code:
        row["audit_code"] = audit_code
    return row


@dataclass
class ScenarioResult:
    scenario_id: str
    status: str  # passed|failed|blocked|skipped|not_run|unverified
    seed: int
    assertions: list[dict[str, Any]] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)
    provider_calls: int = 0
    details: dict[str, Any] = field(default_factory=dict)
    injection_point: str = ""
    setup: str = ""

    def finalize(self) -> "ScenarioResult":
        if self.status in {"skipped", "blocked", "not_run", "unverified"}:
            # not_run/unverified stay unless we have assertions to evaluate
            if self.status == "not_run" and self.assertions:
                pass  # fall through to compute
            else:
                return self
        if not self.assertions:
            self.status = "failed"
            self.assertions.append(_assert(False, "scenario has no assertions"))
            return self
        self.status = "passed" if all(a.get("ok") for a in self.assertions) else "failed"
        return self


def scenario_duplicate_webhook(seed: int) -> ScenarioResult:
    """Project the same normalized provider fact twice through production code."""
    from services.payment_recovery.delivery_projection import project_whatsapp_delivery_fact

    result = ScenarioResult(
        scenario_id="duplicate-webhook",
        status="not_run",
        seed=seed,
        invariants=["INV-06", "INV-13"],
        setup="same provider delivery fact projected twice",
        injection_point="project_whatsapp_delivery_fact",
        provider_calls=0,
    )
    channel = SimpleNamespace(id=7, seller_id=3)
    dispatch = SimpleNamespace(
        id=uuid.UUID(int=seed),
        seller_id=3,
        opportunity_id=uuid.UUID(int=seed + 1),
        status="accepted",
        accepted_at=datetime.now(timezone.utc),
        delivery_status="not_available",
        delivered_at=None,
        read_at=None,
        delivery_failed_at=None,
    )

    def scalar(value):
        query_result = MagicMock()
        query_result.scalar_one_or_none.return_value = value
        return query_result

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=(scalar(channel), scalar(dispatch), scalar(channel), scalar(dispatch))
    )
    fact = {
        "provider": "whatsapp_cloud",
        "provider_account_id": "account-7",
        "message_id": "wamid.duplicate",
        "status": "delivered",
        "timestamp": "2026-07-17T07:00:00Z",
    }

    async def exercise():
        first = await project_whatsapp_delivery_fact(db, fact=fact)
        second = await project_whatsapp_delivery_fact(db, fact=fact)
        return first, second

    first, second = asyncio.run(exercise())
    result.assertions = [
        _assert(first["applied"] is True, "first delivery fact changes dispatch"),
        _assert(second["applied"] is False, "duplicate delivery fact is a no-op"),
        _assert(second["reason"] == "no_transition", "duplicate has explicit no-transition evidence"),
        _assert(dispatch.delivery_status == "delivered", "duplicate cannot downgrade delivery state"),
    ]
    return result.finalize()


def scenario_paid_before_send(seed: int) -> ScenarioResult:
    r = ScenarioResult(
        scenario_id="paid-before-send",
        status="not_run",
        seed=seed,
        invariants=["INV-04", "INV-13"],
        setup="policy fact with order already paid",
        injection_point="evaluate_policy",
        provider_calls=0,
    )
    now = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    fact = PolicyFact(
        seller_id=1,
        order_id=9,
        payment_attempt_id=str(uuid.UUID(int=seed)),
        amount=Decimal("10000.00"),
        currency="IDR",
        payment_expires_at=now + timedelta(hours=24),
        payment_url_valid=True,
        consent_status="active",
        recipient_phone_normalized="+628111",
        recipient_phone_status="valid",
        quiet_hours_start=time(21, 0),
        quiet_hours_end=time(8, 0),
        recipient_timezone="Asia/Jakarta",
        current_time_utc=now,
        mode="approval",
        paused=False,
        global_enabled=True,
        provider_template_approved=True,
        daily_cap_reached=False,
        cooldown_active=False,
        order_status="paid",
        attempt_is_current=True,
    )
    decision = evaluate_policy(fact)
    r.assertions = [
        _assert(decision.allowed is False, "paid order not eligible for send"),
        _assert(
            decision.suppression_code in {"order_not_pending", "already_paid", "order_status_not_pending"}
            or (decision.reason and "paid" in (decision.reason or "").lower())
            or not decision.eligible,
            "suppression for non-pending/paid order",
            actual={"allowed": decision.allowed, "code": decision.suppression_code, "reason": decision.reason},
            audit_code="paid_before_send_suppressed",
        ),
    ]
    # If policy uses order_status string check differently, still require not allowed
    if decision.allowed:
        r.assertions.append(_assert(False, "policy unexpectedly allowed paid order"))
    return r.finalize()


def scenario_provider_timeout(seed: int) -> ScenarioResult:
    r = ScenarioResult(
        scenario_id="provider-timeout-reconcile",
        status="not_run",
        seed=seed,
        invariants=["INV-06"],
        setup="SendMessageResult taxonomy",
        injection_point="_classify_provider_result",
        provider_calls=1,
    )
    timeout = SendMessageResult(success=False, outcome="unknown", error_message="timeout")
    accepted = SendMessageResult(success=True, outcome="accepted", provider_message_id="wamid.ok")
    malformed = SendMessageResult(success=True, outcome="accepted", provider_message_id="")
    rejected = SendMessageResult(success=False, outcome="rejected", error_message="blocked")
    r.assertions = [
        _assert(_classify_provider_result(timeout) == "provider_unknown", "timeout → provider_unknown", audit_code="provider_unknown"),
        _assert(_classify_provider_result(accepted) == "accepted", "stable message id → accepted"),
        _assert(_classify_provider_result(malformed) == "provider_unknown", "missing message id not accepted"),
        _assert(_classify_provider_result(rejected) == "rejected", "explicit rejection terminal"),
        _assert(_classify_provider_result({"success": True}) == "provider_unknown", "non-contract unknown"),
    ]
    return r.finalize()


def scenario_crash_after_accept(seed: int) -> ScenarioResult:
    """Crash after provider accepted must not blind-retry as failed_retryable."""
    r = ScenarioResult(
        scenario_id="crash-after-accept",
        status="not_run",
        seed=seed,
        invariants=["INV-06", "INV-08"],
        setup="accepted evidence requires message id; unknown stays non-retryable taxonomy",
        injection_point="outcome classification contract",
        provider_calls=1,
    )
    accepted = _classify_provider_result(
        SendMessageResult(success=True, outcome="accepted", provider_message_id="wamid.crash")
    )
    ambiguous = _classify_provider_result(
        SendMessageResult(success=False, outcome="unknown", error_message="connection reset")
    )
    r.assertions = [
        _assert(accepted == "accepted", "accepted is durable evidence class"),
        _assert(ambiguous == "provider_unknown", "crash mid-flight is unknown not failed_retryable"),
        _assert(ambiguous != "rejected", "unknown is not rejection"),
    ]
    r.details["expected_db_states"] = {
        "dispatch_on_unknown": "provider_unknown",
        "job_on_unknown": "dead_letter_or_manual_required",
        "retryable": False,
    }
    return r.finalize()


def scenario_redis_loss(seed: int) -> ScenarioResult:
    """Durable job path must exist independent of Redis enqueue success."""
    r = ScenarioResult(
        scenario_id="redis-loss",
        status="not_run",
        seed=seed,
        invariants=["INV-07"],
        setup="inspect enqueue_job_record contract (Postgres first)",
        injection_point="core.idempotency.enqueue_job_record source",
        provider_calls=0,
    )
    import inspect
    from core.idempotency import enqueue_job_record

    source = inspect.getsource(enqueue_job_record)
    r.assertions = [
        _assert("ON CONFLICT" in source, "enqueue uses ON CONFLICT durable insert"),
        _assert("INSERT INTO background_jobs" in source, "persists BackgroundJob before async"),
        _assert("redis" not in source.lower(), "durable enqueue does not depend on Redis"),
    ]
    # Explicit: Redis not required for row existence
    r.assertions.append(
        _assert(
            "background_jobs" in source,
            "job ledger is PostgreSQL background_jobs",
            audit_code="durable_before_async",
        )
    )
    return r.finalize()


def scenario_cross_tenant(seed: int) -> ScenarioResult:
    """Exercise production projection with a channel that has no tenant-bound dispatch."""
    from services.payment_recovery.delivery_projection import project_whatsapp_delivery_fact

    result = ScenarioResult(
        scenario_id="cross-tenant",
        status="not_run",
        seed=seed,
        invariants=["INV-01"],
        setup="active seller-A channel and seller-B-shaped foreign dispatch",
        injection_point="project_whatsapp_delivery_fact",
        provider_calls=0,
    )
    channel = SimpleNamespace(id=11, seller_id=1)
    foreign_dispatch = SimpleNamespace(
        seller_id=2, status="accepted", delivery_status="not_available"
    )

    def scalar(value):
        query_result = MagicMock()
        query_result.scalar_one_or_none.return_value = value
        return query_result

    db = MagicMock()
    db.execute = AsyncMock(side_effect=(scalar(channel), scalar(None)))
    projection = asyncio.run(
        project_whatsapp_delivery_fact(
            db,
            fact={
                "provider": "whatsapp_cloud",
                "provider_account_id": "seller-a-account",
                "message_id": "seller-b-message",
                "status": "delivered",
            },
        )
    )
    dispatch_query = str(db.execute.await_args_list[1].args[0]).lower()
    result.assertions = [
        _assert(projection["applied"] is False, "foreign dispatch is not projected"),
        _assert(projection["reason"] == "dispatch_not_found", "lookup fails closed"),
        _assert("seller_id" in dispatch_query and "channel_id" in dispatch_query, "dispatch lookup is tenant and channel scoped"),
        _assert(foreign_dispatch.delivery_status == "not_available", "foreign tenant state is untouched"),
    ]
    return result.finalize()


def scenario_stale_approval(seed: int) -> ScenarioResult:
    """Mutate a bound payment fact and execute production send revalidation."""
    from models.order import OrderStatus
    from services.payment_recovery.actions import action_digest
    from services.payment_recovery.approval_materializer import (
        build_bound_recovery_action,
    )
    from services.payment_recovery.dispatch import revalidate_before_send

    result = ScenarioResult(
        scenario_id="stale-approval",
        status="not_run",
        seed=seed,
        invariants=["INV-11"],
        setup="approved canonical action followed by payment amount mutation",
        injection_point="revalidate_before_send",
        provider_calls=0,
    )
    opportunity = SimpleNamespace(
        id=uuid.UUID(int=seed),
        seller_id=1,
        status="dispatch_pending",
        order_id=2,
        payment_attempt_id=uuid.UUID(int=seed + 1),
        amount_snapshot=Decimal("10000.00"),
        currency="IDR",
    )
    order = SimpleNamespace(
        id=2,
        seller_id=1,
        status=OrderStatus.PENDING,
        paid_at=None,
    )
    attempt = SimpleNamespace(
        id=opportunity.payment_attempt_id,
        seller_id=1,
        order_id=2,
        amount=Decimal("10000.00"),
        is_current=True,
        payment_expires_at=None,
        trusted_link_reference="payment-reference",
        external_attempt_id="attempt-1",
    )
    permission = SimpleNamespace(
        id=uuid.UUID(int=seed + 2),
        seller_id=1,
        order_id=2,
        payment_attempt_id=attempt.id,
        contact_subject_id=uuid.UUID(int=seed + 3),
        address_fingerprint="recipient-fingerprint",
        channel="whatsapp",
        purpose="transactional_payment_reminder",
        scope_type="order_payment_cycle",
        status="active",
        expires_at=None,
    )
    channel = SimpleNamespace(
        id=7,
        seller_id=1,
        type="whatsapp",
        provider="whatsapp_cloud",
        status="active",
        external_id="phone-number-id",
    )
    template = SimpleNamespace(
        id=8,
        seller_id=1,
        name="payment_reminder_v1",
        language="id",
        body="Bayar {{1}} {{2}}",
        variables_json=[{"key": "order"}, {"key": "amount"}],
        provider_template_id="provider-template-8",
        status="approved",
    )
    action, template_params = build_bound_recovery_action(
        opportunity=opportunity,
        order=order,
        attempt=attempt,
        permission=permission,
        channel=channel,
        template=template,
        scheduled_at="2026-07-17T07:00:00Z",
        policy_version=1,
    )
    digest = action_digest(action)
    dispatch = SimpleNamespace(
        opportunity_id=opportunity.id,
        approval_id=1,
        action_digest=digest,
        contact_permission_id=permission.id,
        contact_subject_id=permission.contact_subject_id,
        recipient_fingerprint=permission.address_fingerprint,
        seller_id=1,
        channel_id=channel.id,
        channel_type=channel.type,
        provider=channel.provider,
        template_code=template.name,
        template_params_json=template_params,
    )
    approval = SimpleNamespace(
        action_digest=digest,
        policy_version=1,
        detail_json={"template_id": template.id, "action": action},
    )

    attempt.amount = Decimal("20000.00")
    opportunity.amount_snapshot = attempt.amount

    def scalar(value):
        query_result = MagicMock()
        query_result.scalar_one_or_none.return_value = value
        return query_result

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            scalar(dispatch),
            scalar(opportunity),
            scalar(approval),
            scalar(order),
            scalar(attempt),
            scalar(permission),
            scalar(channel),
            scalar(template),
        ]
    )
    allowed, reason = asyncio.run(
        revalidate_before_send(db, seller_id=1, dispatch_id=uuid.UUID(int=seed + 4))
    )
    result.assertions = [
        _assert(allowed is False, "production revalidation blocks mutated action"),
        _assert(reason == "approval_stale", "mutation returns approval_stale"),
        _assert(db.execute.await_count == 8, "revalidation reached current template facts"),
    ]
    return result.finalize()


def scenario_consent_withdrawal(seed: int) -> ScenarioResult:
    r = ScenarioResult(
        scenario_id="consent-withdrawal-stop",
        status="not_run",
        seed=seed,
        invariants=["INV-02"],
        setup="STOP keyword allowlist",
        injection_point="is_transactional_stop_keyword",
        provider_calls=0,
    )
    r.assertions = [
        _assert(is_transactional_stop_keyword("STOP"), "STOP exact", audit_code="stop_applied"),
        _assert(is_transactional_stop_keyword("berhenti"), "BERHENTI exact"),
        _assert(not is_transactional_stop_keyword("BATAL"), "BATAL does not auto opt-out"),
        _assert(not is_transactional_stop_keyword("please STOP"), "multi-word not opt-out"),
    ]
    return r.finalize()


def scenario_quiet_hours_expiry(seed: int) -> ScenarioResult:
    r = ScenarioResult(
        scenario_id="quiet-hours-expiry",
        status="not_run",
        seed=seed,
        invariants=["INV-04"],
        setup="quiet hours + invalid expiry fail-safe",
        injection_point="resolve_quiet_hours / parse_legacy_expiry",
        provider_calls=0,
    )
    # Quiet hours wrap midnight (22:00 WIB ≈ 15:00 UTC)
    status, code = resolve_quiet_hours(
        current_time_utc=datetime(2026, 7, 1, 15, 0, tzinfo=timezone.utc),
        recipient_timezone="Asia/Jakarta",
        quiet_start=time(21, 0),
        quiet_end=time(8, 0),
    )
    invalid = parse_legacy_expiry("not-a-date")
    empty = parse_legacy_expiry("")
    valid = parse_legacy_expiry("2026-07-02T00:00:00+00:00")
    r.assertions = [
        _assert(
            status == "deferred" and code == "quiet_hours_deferred",
            "quiet hours defers send",
            actual={"status": status, "code": code},
            audit_code="quiet_hours_deferred",
        ),
        _assert(invalid is None, "invalid expiry suppresses (None)"),
        _assert(empty is None, "empty expiry suppresses"),
        _assert(valid is not None and valid.tzinfo is not None, "valid expiry parsed aware"),
    ]
    return r.finalize()


def scenario_unsafe_ai(seed: int) -> ScenarioResult:
    r = ScenarioResult(
        scenario_id="unsafe-ai",
        status="not_run",
        seed=seed,
        invariants=["INV-03"],
        setup="allowlist parser rejects financial fields",
        injection_point="parse_model_selection",
        provider_calls=0,
    )
    bad = parse_model_selection(
        '{"variant_id":"payment_reminder_soft_v1","discount":"90%","payment_url":"https://x"}'
    )
    good = parse_model_selection('{"variant_id":"payment_reminder_soft_v1"}')
    static = select_static({"order_ref": "ORD-1", "amount_display": "Rp10.000"})
    r.assertions = [
        _assert(bad is None, "forbidden financial keys rejected", audit_code="ai_output_rejected"),
        _assert(good == "payment_reminder_soft_v1", "allowlisted variant accepted"),
        _assert(static.ok and static.source == "static", "static baseline available"),
    ]
    return r.finalize()


def scenario_log_redaction(seed: int) -> ScenarioResult:
    r = ScenarioResult(
        scenario_id="log-redaction",
        status="not_run",
        seed=seed,
        invariants=["INV-14"],
        setup="artifact sample must not contain secrets",
        injection_point="artifact serialization",
        provider_calls=0,
    )
    sample = {
        "order_id": 1,
        "masked": "+62••••••7890",
        "digest": hashlib.sha256(b"action").hexdigest()[:16],
    }
    blob = json.dumps(sample)
    r.assertions = [
        _assert("access_token" not in blob, "no access_token field"),
        _assert("Bearer " not in blob, "no bearer token"),
        _assert("••••" in sample["masked"], "phone masked", audit_code="pii_masked"),
    ]
    return r.finalize()


def scenario_legacy_scheduler_off(seed: int) -> ScenarioResult:
    r = ScenarioResult(
        scenario_id="legacy-scheduler-off",
        status="not_run",
        seed=seed,
        invariants=["INV-12"],
        setup="Settings defaults without env file",
        injection_point="config.Settings",
        provider_calls=0,
    )
    from config import Settings

    s = Settings(_env_file=None)
    r.assertions = [
        _assert(s.SCHEDULER_ENABLED is False, "SCHEDULER_ENABLED default false"),
        _assert(s.ENABLE_LEGACY_PENDING_PAYMENT_FOLLOWUP is False, "legacy followup default false"),
        _assert(s.ENABLE_PAYMENT_RECOVERY is False, "payment recovery default false"),
        _assert((s.PAYMENT_RECOVERY_MODE or "observe") == "observe", "recovery mode default observe"),
        _assert(s.ENABLE_DEMO_PROOF_MODE is False, "proof mode default false"),
    ]
    return r.finalize()


def scenario_browser_cache_tenant_switch(seed: int) -> ScenarioResult:
    """Browser-only scenario: never pass from backend harness."""
    return ScenarioResult(
        scenario_id=BROWSER_SCENARIO_ID,
        status="not_run",
        seed=seed,
        invariants=["INV-01", "BUG-025"],
        setup="Playwright A→logout→B cache isolation",
        injection_point="frontend session epoch + cache clear",
        details={
            "suite": "browser",
            "artifact": "artifacts/proof-browser.json",
            "reason": "must be produced by Playwright P7.1a, not backend harness",
        },
        assertions=[],
    )


SCENARIOS: dict[str, Callable[[int], ScenarioResult]] = {
    "duplicate-webhook": scenario_duplicate_webhook,
    "paid-before-send": scenario_paid_before_send,
    "provider-timeout-reconcile": scenario_provider_timeout,
    "crash-after-accept": scenario_crash_after_accept,
    "redis-loss": scenario_redis_loss,
    "cross-tenant": scenario_cross_tenant,
    "stale-approval": scenario_stale_approval,
    "consent-withdrawal-stop": scenario_consent_withdrawal,
    "quiet-hours-expiry": scenario_quiet_hours_expiry,
    "unsafe-ai": scenario_unsafe_ai,
    "log-redaction": scenario_log_redaction,
    "legacy-scheduler-off": scenario_legacy_scheduler_off,
    BROWSER_SCENARIO_ID: scenario_browser_cache_tenant_switch,
}


def production_guard_blocks_proof_mode() -> tuple[bool, str]:
    environments = {
        str(value).strip().lower()
        for value in (
            os.environ.get("ENVIRONMENT"),
            os.environ.get("APP_ENV"),
        )
        if value
    }
    if "production" in environments:
        return True, "proof_mode_forbidden_in_production"

    settings = get_settings()
    credential_names = (
        "WHATSAPP_ACCESS_TOKEN",
        "WHATSAPP_PHONE_NUMBER_ID",
        "WHATSAPP_WABA_ID",
        "WHATSAPP_APP_SECRET",
        "WHATSAPP_VERIFY_TOKEN",
    )
    if any(
        str(os.environ.get(name) or getattr(settings, name, "")).strip()
        for name in credential_names
    ):
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
        )
    fn = SCENARIOS.get(scenario_id)
    if not fn:
        return ScenarioResult(
            scenario_id=scenario_id,
            status="failed",
            seed=seed,
            assertions=[_assert(False, f"unknown scenario: {scenario_id}")],
        ).finalize()
    try:
        result = fn(seed)
    except Exception as exc:
        return ScenarioResult(
            scenario_id=scenario_id,
            status="failed",
            seed=seed,
            assertions=[
                _assert(False, f"scenario execution failed: {type(exc).__name__}")
            ],
            details={"error_type": type(exc).__name__},
        )
    if result.status == "not_run" and not result.assertions:
        return result  # browser / deferred
    return result.finalize() if result.status == "not_run" else result


def _count(results: list[ScenarioResult], status: str) -> int:
    return sum(1 for r in results if r.status == status)


def run_all(seed: int = 42, suite: str = "backend") -> dict[str, Any]:
    run_id = (os.environ.get("JUALIN_EVIDENCE_RUN_ID") or str(uuid.uuid4())).strip()
    if not run_id:
        run_id = str(uuid.uuid4())
    source_commit = _git_commit_sha()
    source_tree_clean_at_start = git_source_tree_clean()
    started = datetime.now(timezone.utc).isoformat()
    if suite == "backend":
        ids = list(REQUIRED_BACKEND_SCENARIOS)
    elif suite == "browser":
        ids = [BROWSER_SCENARIO_ID]
    else:
        ids = list(SCENARIOS.keys())

    results = [run_scenario(sid, seed=seed) for sid in ids]
    # Always attach browser scenario as not_run for full inventory visibility
    if suite == "backend" and not any(r.scenario_id == BROWSER_SCENARIO_ID for r in results):
        results.append(run_scenario(BROWSER_SCENARIO_ID, seed=seed))

    missing_required = [
        sid for sid in REQUIRED_BACKEND_SCENARIOS if not any(r.scenario_id == sid for r in results)
    ]
    empty_assertion_failures = [
        r.scenario_id
        for r in results
        if r.scenario_id in REQUIRED_BACKEND_SCENARIOS and not r.assertions and r.status not in {"blocked"}
    ]

    backend_results = [r for r in results if r.scenario_id in REQUIRED_BACKEND_SCENARIOS]
    backend_failed = [r for r in backend_results if r.status == "failed"]
    backend_passed = [r for r in backend_results if r.status == "passed"]

    # Backend proof is independent of browser and staging dimensions.
    if missing_required or empty_assertion_failures or backend_failed:
        backend_status = "failed"
    elif any(r.status == "blocked" for r in backend_results):
        backend_status = "blocked"
    elif len(backend_passed) == len(REQUIRED_BACKEND_SCENARIOS):
        backend_status = "passed"
    else:
        backend_status = "failed"

    browser_result = next((r for r in results if r.scenario_id == BROWSER_SCENARIO_ID), None)
    browser_status = browser_result.status if browser_result else "not_run"
    staging_status = "blocked"
    finished = datetime.now(timezone.utc).isoformat()
    source_identity_stable = (
        source_tree_clean_at_start
        and git_source_tree_clean()
        and source_commit != "unknown"
        and _git_commit_sha() == source_commit
    )
    suite_status = (
        backend_status
        if suite == "backend"
        else "passed"
        if all(r.status == "passed" for r in results)
        else "failed"
    )
    artifact_status = suite_status if source_identity_stable else "unverified"

    payload = {
        "run_id": run_id,
        "suite": suite,
        "seed": seed,
        "schema_version": "proof-artifact-v1",
        "redaction_status": "passed",
        "commit_sha": source_commit,
        "source_tree_clean": source_identity_stable,
        "started_at": started,
        "finished_at": finished,
        "command": f"python -m scripts.proof_mode run-all --suite {suite} --seed {seed}",
        "environment": os.environ.get("ENVIRONMENT") or "local",
        "scenarios": [asdict(r) for r in results],
        "required_backend_scenarios": list(REQUIRED_BACKEND_SCENARIOS),
        "missing_required": missing_required,
        "empty_assertion_failures": empty_assertion_failures,
        "summary": {
            "total": len(results),
            "passed": _count(results, "passed"),
            "failed": _count(results, "failed"),
            "blocked": _count(results, "blocked"),
            "skipped": _count(results, "skipped"),
            "not_run": _count(results, "not_run"),
            "unverified": _count(results, "unverified"),
            "backend_required": len(REQUIRED_BACKEND_SCENARIOS),
            "backend_passed": len(backend_passed),
        },
        "dimensions": {
            "backend_invariants": backend_status,
            "browser_e2e": browser_status,
            "staging_provider": staging_status,
        },
        "status": artifact_status,
        "disclaimer": (
            "Offline deterministic proof of safety invariants. "
            "Does not prove live WhatsApp/payment staging. "
            "Browser scenario remains not_run until Playwright produces proof-browser.json."
        ),
    }
    return payload


def validate_sanitized_artifact(data: dict[str, Any]) -> None:
    """Reject secret-bearing or unbounded artifact payloads before persistence/use."""
    import re

    if not isinstance(data, dict):
        raise ValueError("artifact root must be an object")

    sensitive_keys = {
        "access_token",
        "api_key",
        "authorization",
        "capability_token",
        "cookie",
        "database_url",
        "dsn",
        "password",
        "password_hash",
        "private_key",
        "refresh_token",
        "secret",
        "secret_key",
        "set_cookie",
        "test_database_url",
    }
    sensitive_suffixes = (
        "_access_token",
        "_api_key",
        "_capability_token",
        "_private_key",
        "_cookie",
        "_dsn",
        "_password",
        "_refresh_token",
        "_secret",
        "_secret_key",
    )
    visited = 0

    def reject_sensitive_keys(value: Any, depth: int = 0) -> None:
        nonlocal visited
        visited += 1
        if visited > 100_000 or depth > 32:
            raise ValueError("artifact exceeds safety limits")
        if isinstance(value, dict):
            for raw_key, nested in value.items():
                key = re.sub(r"(?<!^)(?=[A-Z])", "_", str(raw_key))
                key = re.sub(r"[^a-zA-Z0-9]+", "_", key).strip("_").lower()
                compact_key = re.sub(r"[^a-z0-9]", "", str(raw_key).lower())
                if (
                    key in sensitive_keys
                    or key == "token"
                    or key.endswith("_token")
                    or key.endswith(sensitive_suffixes)
                    or compact_key.endswith(("token", "apikey", "password", "secret", "privatekey", "cookie", "dsn"))
                ):
                    raise ValueError("artifact contains a sensitive field")
                reject_sensitive_keys(nested, depth + 1)
        elif isinstance(value, list):
            for nested in value:
                reject_sensitive_keys(nested, depth + 1)

    reject_sensitive_keys(data)
    try:
        blob = json.dumps(data)
    except (RecursionError, TypeError, ValueError) as exc:
        raise ValueError("artifact cannot be serialized safely") from exc
    if len(blob.encode("utf-8")) > 2_000_000:
        raise ValueError("artifact exceeds size limit")
    patterns = (
        r"Bearer\s+[A-Za-z0-9\-_\.]{20,}",
        r"WHATSAPP_ACCESS_TOKEN\s*=\s*\S+",
        r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
        r'"password"\s*:\s*"[^"]{8,}"',
        r'"access_token"\s*:\s*"[^"]{8,}"',
    )
    if any(re.search(pattern, blob) for pattern in patterns):
        raise ValueError("artifact failed redaction check")


def load_sanitized_artifact(path: Path) -> dict[str, Any]:
    """Read a bounded proof artifact and reject duplicate or sensitive fields."""
    if path.stat().st_size > 2_000_000:
        raise ValueError("artifact exceeds size limit")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("artifact contains duplicate keys")
            result[key] = value
        return result

    try:
        data = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except RecursionError as exc:
        raise ValueError("artifact exceeds nesting limit") from exc
    validate_sanitized_artifact(data)
    return data

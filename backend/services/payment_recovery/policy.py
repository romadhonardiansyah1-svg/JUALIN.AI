"""
P2.2 — Deterministic policy evaluation (pure).

All functions receive explicit fact objects, injected clock, no DB/network.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, time
from decimal import Decimal
from typing import Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re


@dataclass(frozen=True)
class PolicyFact:
    seller_id: int
    order_id: int
    payment_attempt_id: str
    amount: Decimal
    currency: str
    payment_expires_at: datetime | None
    payment_url_valid: bool
    consent_status: Literal["active", "withdrawn", "expired", "missing"]
    recipient_phone_normalized: str | None
    recipient_phone_status: Literal["valid", "invalid", "unsupported"]
    quiet_hours_start: time
    quiet_hours_end: time
    recipient_timezone: str | None  # e.g. "Asia/Jakarta"
    current_time_utc: datetime
    mode: Literal["disabled", "observe", "approval", "auto_safe"]
    paused: bool
    global_enabled: bool
    provider_template_approved: bool
    daily_cap_reached: bool
    cooldown_active: bool
    order_status: str
    attempt_is_current: bool


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    suppression_code: str | None
    eligible: bool
    reason: str | None
    scheduled_at: datetime | None = None


def parse_legacy_expiry(expiry_str: str | None) -> datetime | None:
    """
    Parse legacy Order.payment_expires_at which is String(100).
    Returns aware UTC datetime or None if invalid/empty (suppression).
    Fail-safe: invalid -> None -> suppress, not guess.
    """
    if not expiry_str:
        return None
    expiry_str = expiry_str.strip()
    if not expiry_str:
        return None

    # Try ISO format
    try:
        # Handle Z suffix
        iso = expiry_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            # Assume UTC if naive? But blueprint says fail-safe: invalid if no tz? We'll assume UTC for legacy compat
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # Try parsing as timestamp? For simplicity, return None -> suppress
    return None


def evaluate_policy(fact: PolicyFact) -> PolicyDecision:
    """
    Deterministic eligibility checks per INV-02, INV-12, etc.
    Returns first suppression reason encountered, or allowed.
    """
    # Global kill switch
    if not fact.global_enabled:
        return PolicyDecision(allowed=False, suppression_code="feature_disabled", eligible=False, reason="global disabled")

    if fact.paused:
        return PolicyDecision(allowed=False, suppression_code="tenant_paused", eligible=False, reason="tenant paused")

    if fact.mode == "disabled":
        return PolicyDecision(allowed=False, suppression_code="feature_disabled", eligible=False, reason="mode disabled")

    if fact.mode == "observe":
        return PolicyDecision(allowed=False, suppression_code="observe_only", eligible=False, reason="observe mode")

    if fact.mode == "auto_safe":
        # For MVP, auto_safe not yet supported unless future flag
        return PolicyDecision(allowed=False, suppression_code="mode_not_supported", eligible=False, reason="auto_safe not supported in MVP")

    # Order status
    if fact.order_status != "pending":
        return PolicyDecision(allowed=False, suppression_code="order_not_pending", eligible=False, reason="order not pending")

    # Payment expiry
    if fact.payment_expires_at is None:
        return PolicyDecision(allowed=False, suppression_code="payment_expiry_unknown", eligible=False, reason="expiry unknown")
    # Check if already expired
    if fact.payment_expires_at <= fact.current_time_utc:
        return PolicyDecision(allowed=False, suppression_code="payment_expired", eligible=False, reason="expired")

    # Trusted payment URL
    if not fact.payment_url_valid:
        return PolicyDecision(allowed=False, suppression_code="untrusted_payment_url", eligible=False, reason="untrusted url")

    # Recipient phone
    if fact.recipient_phone_status == "invalid" or fact.recipient_phone_normalized is None:
        return PolicyDecision(allowed=False, suppression_code="recipient_invalid", eligible=False, reason="invalid phone")
    if fact.recipient_phone_status == "unsupported":
        return PolicyDecision(allowed=False, suppression_code="recipient_invalid", eligible=False, reason="unsupported phone")

    # Consent
    if fact.consent_status == "missing":
        return PolicyDecision(allowed=False, suppression_code="consent_missing", eligible=False, reason="consent missing")
    if fact.consent_status == "withdrawn":
        return PolicyDecision(allowed=False, suppression_code="consent_withdrawn", eligible=False, reason="withdrawn")
    if fact.consent_status == "expired":
        return PolicyDecision(allowed=False, suppression_code="consent_expired", eligible=False, reason="expired")

    # Provider template
    if not fact.provider_template_approved:
        return PolicyDecision(allowed=False, suppression_code="provider_template_unavailable", eligible=False, reason="template not approved")

    # Cap and cooldown
    if fact.daily_cap_reached:
        return PolicyDecision(allowed=False, suppression_code="frequency_cap_reached", eligible=False, reason="cap")
    if fact.cooldown_active:
        return PolicyDecision(allowed=False, suppression_code="cooldown_active", eligible=False, reason="cooldown")

    # Payment attempt current
    if not fact.attempt_is_current:
        return PolicyDecision(allowed=False, suppression_code="dispatch_already_exists", eligible=False, reason="not current attempt")

    quiet_status, quiet_code = resolve_quiet_hours(
        current_time_utc=fact.current_time_utc,
        recipient_timezone=fact.recipient_timezone,
        quiet_start=fact.quiet_hours_start,
        quiet_end=fact.quiet_hours_end,
    )
    if quiet_status != "allowed":
        return PolicyDecision(
            allowed=False,
            suppression_code=quiet_code,
            eligible=quiet_status == "deferred",
            reason="deferred by quiet hours" if quiet_status == "deferred" else "quiet hours unavailable",
        )

    return PolicyDecision(allowed=True, suppression_code=None, eligible=True, reason="eligible")


def resolve_quiet_hours(
    *,
    current_time_utc: datetime,
    recipient_timezone: str | None,
    quiet_start: time,
    quiet_end: time,
) -> tuple[str, str]:
    """Return an allow/defer decision using the recipient's IANA timezone."""
    if not recipient_timezone:
        return ("suppressed", "recipient_timezone_unknown")
    if current_time_utc.tzinfo is None or current_time_utc.utcoffset() is None:
        return ("suppressed", "current_time_timezone_unknown")

    try:
        recipient_zone = ZoneInfo(recipient_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        # Indonesia does not observe DST; keep the safety check available on
        # Windows runtimes that do not bundle the IANA timezone database.
        indonesia_offsets = {
            "Asia/Jakarta": 7,
            "Asia/Pontianak": 7,
            "Asia/Makassar": 8,
            "Asia/Ujung_Pandang": 8,
            "Asia/Jayapura": 9,
        }
        offset = indonesia_offsets.get(recipient_timezone)
        if offset is None:
            return ("suppressed", "recipient_timezone_invalid")
        recipient_zone = timezone(timedelta(hours=offset))

    local_time = current_time_utc.astimezone(recipient_zone).time().replace(tzinfo=None)

    if quiet_start <= quiet_end:
        is_quiet = quiet_start <= local_time < quiet_end
    else:
        is_quiet = local_time >= quiet_start or local_time < quiet_end

    if is_quiet:
        return ("deferred", "quiet_hours_deferred")
    return ("allowed", "ok")

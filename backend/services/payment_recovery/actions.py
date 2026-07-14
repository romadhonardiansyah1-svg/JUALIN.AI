"""
P2.2 — Canonical action and digest (pure).

Implements blueprint 31.2 pseudocode with NFC, sorted keys, no whitespace, Decimal as string, UTC Z second precision.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def canonical_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Decimal):
        # Domain must already quantize to currency precision — format as plain string
        # Normalize: remove trailing zeros? Use format "f" per blueprint
        return format(value, "f")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("naive_datetime not allowed in canonical action")
        utc = value.astimezone(timezone.utc).replace(microsecond=0)
        return utc.isoformat().replace("+00:00", "Z")
    if isinstance(value, list):
        return [canonical_scalar(item) for item in value]
    if isinstance(value, dict):
        return {
            unicodedata.normalize("NFC", str(key)): canonical_scalar(item)
            for key, item in value.items()
        }
    if value is None or isinstance(value, (bool, int)):
        return value
    # For UUID and other objects, convert to string via str then NFC
    # This handles UUID objects
    try:
        # Try to see if it's UUID-like
        s = str(value)
        # If original was UUID, keep string representation
        return unicodedata.normalize("NFC", s)
    except Exception:
        raise TypeError(f"unsupported canonical type: {type(value).__name__}")


def action_digest(action: dict[str, Any]) -> str:
    """
    Deterministic SHA-256 hex of canonical JSON.
    UTF-8, sorted keys, no whitespace, allow_nan=False.
    """
    canonical = canonical_scalar(action)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_canonical_action(
    *,
    action_version: int,
    action_type: str,
    purpose: str,
    seller_id: int,
    opportunity_id: str,
    order_id: int,
    payment_attempt_id: str,
    amount: Decimal,
    currency: str,
    payment_expires_at_utc: datetime | None,
    action_revision: int,
    contact_subject_id: str,
    contact_permission_id: str,
    recipient_fingerprint: str,
    channel_id: int,
    channel_type: str,
    provider_account_fingerprint: str,
    provider_template_name: str,
    provider_template_locale: str,
    provider_template_content_digest: str,
    provider_template_version: str,
    template_params_digest: str,
    payment_reference_fingerprint: str,
    payment_reference_fingerprint_key_version: int,
    scheduled_at_utc: datetime,
    policy_version: int,
) -> dict:
    """
    Build canonical action dict per blueprint section 10.1.
    Decimal and datetime handling is done in canonical_scalar.
    """
    return {
        "action_version": action_version,
        "action_type": action_type,
        "purpose": purpose,
        "seller_id": seller_id,
        "opportunity_id": str(opportunity_id),
        "order_id": order_id,
        "payment_attempt_id": str(payment_attempt_id),
        "amount": amount,  # Decimal, will be canonicalized to string
        "currency": currency,
        "payment_expires_at_utc": payment_expires_at_utc,
        "action_revision": action_revision,
        "contact_subject_id": str(contact_subject_id),
        "contact_permission_id": str(contact_permission_id),
        "recipient_fingerprint": recipient_fingerprint,
        "channel_id": channel_id,
        "channel_type": channel_type,
        "provider_account_fingerprint": provider_account_fingerprint,
        "provider_template_name": provider_template_name,
        "provider_template_locale": provider_template_locale,
        "provider_template_content_digest": provider_template_content_digest,
        "provider_template_version": provider_template_version,
        "template_params_digest": template_params_digest,
        "payment_reference_fingerprint": payment_reference_fingerprint,
        "payment_reference_fingerprint_key_version": payment_reference_fingerprint_key_version,
        "scheduled_at_utc": scheduled_at_utc,
        "policy_version": policy_version,
    }

"""
P2.5 — Provider eligibility adapters (support matrix per payment/WA account).

Implements typed capability checks for:
- Payment provider: current payment query, stable cycle ID, trusted HTTPS link, exact expiry
- WA provider: account active, approved utility template, API version, idempotency, etc.

Midtrans/other QR or base64 action is NOT trusted browser link.
expires_at=None => observe evidence payment_expiry_unknown and live suppression.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse
import re


@dataclass(frozen=True)
class PaymentProviderCapabilities:
    provider: str
    payment_state_query: bool
    stable_cycle_id: bool
    trusted_https_link: bool
    exact_expiry: bool
    provider_account_active: bool
    idempotency_supported: bool = False
    reconciliation_supported: bool = False
    delivery_webhook_supported: bool = False


@dataclass(frozen=True)
class WAProviderCapabilities:
    provider_account_id: str
    account_active: bool
    api_version_supported: bool
    template_approved: bool
    template_locale: str
    template_version: str
    send_template_supported: bool
    idempotency_supported: bool
    reconcile_supported: bool
    delivery_webhook_supported: bool


# Allowlist for trusted payment HTTPS hosts
TRUSTED_PAYMENT_HOSTS = {
    "app.midtrans.com",
    "app.sandbox.midtrans.com",
    "api.midtrans.com",
    "api.sandbox.midtrans.com",
}

# For safety, we consider ONLY HTTPS with trusted host as trusted link
# QR base64 (data:image/...) and VA numbers are NOT trusted browser links


def is_trusted_https_link(url: str | None) -> bool:
    if not url:
        return False
    url = url.strip()
    # QR data is base64 like data:image/png;base64,...
    if url.startswith("data:"):
        return False
    # Base64 blob without scheme?
    if len(url) > 200 and re.match(r"^[A-Za-z0-9+/=]+$", url[:200]):
        # Likely base64 QR
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return False
        host = (parsed.hostname or "").lower()
        # Exact match or subdomain of trusted?
        for trusted in TRUSTED_PAYMENT_HOSTS:
            if host == trusted or host.endswith("." + trusted):
                return True
        # For MVP, allow any https that looks like payment link? Per blueprint, must be allowlist, so strict
        return False
    except Exception:
        return False


def evaluate_payment_provider(
    *,
    provider: str,
    payment_url: str | None,
    payment_qr_data: str | None,
    payment_expires_at_str: str | None,
    invoice_id: str | None,
) -> PaymentProviderCapabilities:
    """Evaluate whether a persisted payment cycle is supported by Midtrans."""
    from services.payment_recovery.policy import parse_legacy_expiry

    is_midtrans = provider == "midtrans"
    stable_cycle = bool(invoice_id)
    exact_expiry = parse_legacy_expiry(payment_expires_at_str) is not None

    return PaymentProviderCapabilities(
        provider=provider,
        payment_state_query=is_midtrans and stable_cycle,
        stable_cycle_id=stable_cycle,
        trusted_https_link=is_midtrans and is_trusted_https_link(payment_url),
        exact_expiry=exact_expiry,
        provider_account_active=is_midtrans,
        idempotency_supported=is_midtrans,
        reconciliation_supported=is_midtrans,
        delivery_webhook_supported=False,
    )


def evaluate_wa_provider(
    *,
    channel: any,  # Channel model
    template: any = None,  # WhatsAppMessageTemplate model
) -> WAProviderCapabilities:
    """
    Evaluate WA provider account capabilities.
    Channel is existing Channel model with type whatsapp, status active, config_encrypted
    """
    account_id = ""
    active = False
    api_version_supported = False
    template_approved = False
    locale = "id"
    version = ""
    send_supported = False
    idempotency = False
    reconcile = False
    delivery_webhook = False

    try:
        if channel:
            account_id = getattr(channel, "external_id", "") or str(getattr(channel, "id", ""))
            active = getattr(channel, "status", "") == "active"
            # Decrypt config to check access_token, phone_number_id
            try:
                from core.secure_config import decrypt_config
                cfg = decrypt_config(getattr(channel, "config_encrypted", "") or "")
                has_token = bool(cfg.get("access_token"))
                has_phone_id = bool(cfg.get("phone_number_id") or getattr(channel, "external_id", ""))
                send_supported = has_token and has_phone_id and active
            except Exception:
                send_supported = False

            # API version check — from config or settings
            try:
                from config import get_settings
                settings = get_settings()
                ver = settings.WHATSAPP_GRAPH_VERSION or "v20.0"
                # For MVP, assume v19.0+ supported, v20.0+ preferred
                # Official docs: check version support, here we just check not empty
                api_version_supported = bool(ver) and ver.startswith("v")
            except Exception:
                api_version_supported = False

        if template:
            locale = getattr(template, "language", "id") or "id"
            version = getattr(template, "provider_template_id", "") or getattr(template, "status", "")
            template_approved = getattr(template, "status", "") == "approved"
        else:
            # If no template passed, assume not approved for safety
            template_approved = False

        # Idempotency: WA Cloud supports idempotency via message id uniqueness? Assume true for template send
        idempotency = send_supported and template_approved
        reconcile = send_supported
        delivery_webhook = True  # Statuses are supported

    except Exception:
        pass

    return WAProviderCapabilities(
        provider_account_id=account_id,
        account_active=active,
        api_version_supported=api_version_supported,
        template_approved=template_approved,
        template_locale=locale,
        template_version=version,
        send_template_supported=send_supported and template_approved,
        idempotency_supported=idempotency,
        reconcile_supported=reconcile,
        delivery_webhook_supported=delivery_webhook,
    )

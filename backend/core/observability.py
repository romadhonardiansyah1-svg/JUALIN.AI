"""
Sentry initialization — inert unless SENTRY_DSN is set.

Error tracking plus a small tracing sample. No profiling, no PII: this app handles
customer phone numbers, addresses and payment capability tokens, none of which may
leave the server.
"""
from urllib.parse import parse_qsl, urlencode

from config import get_settings
from core.logging_config import get_logger

logger = get_logger(__name__)

# Extra keys scrubbed on top of sentry_sdk's DEFAULT_DENYLIST + DEFAULT_PII_DENYLIST.
# Names mirror the actual column/field names used across models and routes.
# EventScrubber matches keys EXACTLY (scrubber.py:117), so every real variant has
# to be listed: "token" in DEFAULT_DENYLIST does not cover "raw_token".
_EXTRA_DENYLIST = [
    # contact / identity PII
    "no_hp",
    "phone",
    "customer_phone",
    "customer_address",
    "customer_name",
    "customer_email",
    "email",
    "whatsapp_id",
    "recipient",
    "recipient_fingerprint",
    "address",
    "address_book",
    "alamat",
    "password_hash",
    # payment capability tokens
    "payment_access_token",
    "payment_access_token_hmac",
    "capability_token",
    "raw_token",
    "raw_session_token",
    "session_token",
    "session_token_hmac",
    "token_hmac",
    "bootstrap_token",
    "access_token",
    "refresh_token",
    "preview_token",
    # payment instrument data + links that embed ?token=
    "payment_url",
    "payment_va_number",
    "va_number",
    "payment_qr_data",
    "qr_data",
    # provider secrets
    "signature_key",
    "server_key",
    "client_key",
    "ciphertext",
    "idempotency_key",
]

# Query-parameter names whose values must never reach Sentry. Matched as a
# case-insensitive SUBSTRING (unlike EventScrubber), so "token" also covers
# "payment_access_token" / "bootstrap_token".
_QS_SENSITIVE_TERMS = (
    "token", "secret", "password", "passwd", "pwd", "key", "auth", "jwt",
    "bearer", "session", "sid", "credential", "signature", "hmac", "otp",
    "email", "phone", "alamat", "address",
)

_FILTERED = "[Filtered]"


def _is_sensitive_param(name: str) -> bool:
    lowered = name.lower()
    return any(term in lowered for term in _QS_SENSITIVE_TERMS)


def _scrub_query_string(qs: object) -> object:
    """Replace sensitive query-parameter VALUES with [Filtered], keep the names.

    The SDK sends query_string as a str (``_get_query`` in
    sentry_sdk/integrations/_asgi_common.py:81-88), but the Sentry protocol also
    allows a dict, so both shapes are handled.
    """
    if isinstance(qs, dict):
        return {
            k: (_FILTERED if isinstance(k, str) and _is_sensitive_param(k) else v)
            for k, v in qs.items()
        }
    if not isinstance(qs, str) or not qs:
        return qs
    pairs = parse_qsl(qs, keep_blank_values=True)
    if not pairs:
        # Unparseable / non key=value query string: drop it rather than guess.
        return _FILTERED
    return urlencode(
        [(k, _FILTERED if _is_sensitive_param(k) else v) for k, v in pairs],
        safe="[]",
    )


def scrub_event_request(event: object, hint: object = None) -> object:
    """before_send hook: scrub query-string values the EventScrubber misses.

    sentry_sdk's EventScrubber only walks request headers/cookies/data
    (sentry_sdk/scrubber.py:123-131) while the ASGI integration attaches
    query_string unconditionally when data_collection is unset
    (sentry_sdk/integrations/_asgi_common.py:140-141). Without this hook a
    request to /api/payments/public/status/{id}?token=... ships the payment
    capability token to Sentry in plaintext.
    """
    if not isinstance(event, dict):
        return event
    request = event.get("request")
    if not isinstance(request, dict):
        return event

    if "query_string" in request:
        request["query_string"] = _scrub_query_string(request["query_string"])

    # _get_url() builds the URL without the query string, but other integrations
    # (and future SDK versions) may not; strip anything after "?" defensively.
    url = request.get("url")
    if isinstance(url, str) and "?" in url:
        base, _, query = url.partition("?")
        scrubbed = _scrub_query_string(query)
        request["url"] = f"{base}?{scrubbed}" if isinstance(scrubbed, str) else base

    return event


def init_sentry() -> bool:
    """Initialize Sentry if configured. Returns True when enabled."""
    settings = get_settings()
    dsn = (settings.SENTRY_DSN or "").strip()
    if not dsn:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.scrubber import DEFAULT_DENYLIST, DEFAULT_PII_DENYLIST, EventScrubber
    except ImportError:
        logger.warning("SENTRY_DSN set but sentry-sdk is not installed; skipping init")
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.SENTRY_ENVIRONMENT,
        release=f"{settings.APP_NAME}@{settings.APP_VERSION}",
        traces_sample_rate=max(0.0, min(1.0, settings.SENTRY_TRACES_SAMPLE_RATE)),
        send_default_pii=False,
        max_request_body_size="never",
        # EventScrubber never touches request.query_string; transaction events
        # carry a request payload too, hence both hooks.
        before_send=scrub_event_request,
        before_send_transaction=scrub_event_request,
        event_scrubber=EventScrubber(
            denylist=DEFAULT_DENYLIST + DEFAULT_PII_DENYLIST + _EXTRA_DENYLIST,
            recursive=True,
        ),
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
        ],
    )
    logger.info(
        "Sentry enabled",
        extra={
            "environment": settings.SENTRY_ENVIRONMENT,
            "traces_sample_rate": settings.SENTRY_TRACES_SAMPLE_RATE,
        },
    )
    return True

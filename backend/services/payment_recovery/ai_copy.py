"""
P5.3 — Bounded AI template variant selection for recovery reminders.

LLM may only choose an allowlisted variant id. It cannot invent recipient,
amount, discount, payment URL, or free-form body. Invalid/timeout → static
baseline or no_send according to seller setting.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from core.logging_config import get_logger

logger = get_logger(__name__)

# Immutable allowlisted utility variants. Body templates use placeholders only;
# final render fills redacted/canonical facts from deterministic code.
APPROVED_VARIANTS: dict[str, dict[str, Any]] = {
    "payment_reminder_soft_v1": {
        "template_code": "payment_reminder_soft_v1",
        "language": "id",
        "body_template": (
            "Halo, pesanan {{order_ref}} senilai {{amount_display}} masih menunggu "
            "pembayaran. Selesaikan lewat tautan pembayaran resmi toko."
        ),
        "param_keys": ["order_ref", "amount_display"],
    },
    "payment_reminder_clear_v1": {
        "template_code": "payment_reminder_clear_v1",
        "language": "id",
        "body_template": (
            "Pengingat: {{order_ref}} ({{amount_display}}) belum dibayar. "
            "Gunakan tautan pembayaran resmi yang sudah disediakan."
        ),
        "param_keys": ["order_ref", "amount_display"],
    },
}

STATIC_BASELINE_VARIANT = "payment_reminder_soft_v1"
FORBIDDEN_BODY_PATTERNS = (
    re.compile(r"diskon\s*\d", re.I),
    re.compile(r"gratis", re.I),
    re.compile(r"https?://", re.I),
    re.compile(r"\btransfer\s+ke\b", re.I),
    re.compile(r"\b\d{10,}\b"),  # raw long numbers / phones
)

FallbackMode = Literal["static", "no_send"]


@dataclass(frozen=True)
class SelectionResult:
    ok: bool
    variant_id: str | None
    template_code: str | None
    language: str | None
    rendered_preview: str | None
    source: Literal["ai", "static", "rejected"]
    reason: str
    model: str | None = None
    prompt_version: str = "recovery_variant_select_v1"


def _redacted_facts(facts: dict[str, Any]) -> dict[str, str]:
    order_ref = str(facts.get("order_ref") or facts.get("order_id") or "ORD")
    amount_display = str(facts.get("amount_display") or facts.get("amount") or "")
    # Never pass raw phone, token, or full payment URL into the selector prompt.
    return {
        "order_ref": order_ref[:40],
        "amount_display": amount_display[:40],
        "currency": str(facts.get("currency") or "IDR")[:3],
        "locale": str(facts.get("locale") or "id")[:8],
    }


def render_variant(variant_id: str, facts: dict[str, Any]) -> str | None:
    variant = APPROVED_VARIANTS.get(variant_id)
    if not variant:
        return None
    redacted = _redacted_facts(facts)
    text = variant["body_template"]
    for key in variant["param_keys"]:
        text = text.replace("{{" + key + "}}", redacted.get(key, ""))
    if "{{" in text:
        return None
    for pat in FORBIDDEN_BODY_PATTERNS:
        if pat.search(text):
            # Rendered body should not introduce forbidden free-form; placeholders only.
            # amount_display may contain digits — allow currency digits but not bare long phones.
            if pat.pattern.startswith(r"\b\d") and redacted.get("amount_display"):
                continue
            return None
    return text


def validate_variant_id(variant_id: object) -> str | None:
    if not isinstance(variant_id, str):
        return None
    vid = variant_id.strip()
    if vid in APPROVED_VARIANTS:
        return vid
    return None


def parse_model_selection(raw: str) -> str | None:
    """Accept only structured {\"variant_id\": \"...\"} from model output."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    # Strip optional markdown fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    # Reject extra action fields that try to authorize finance
    forbidden_keys = {
        "amount",
        "discount",
        "payment_url",
        "recipient",
        "phone",
        "schedule",
        "approve",
        "send",
    }
    if forbidden_keys.intersection(data.keys()):
        return None
    return validate_variant_id(data.get("variant_id"))


def select_static(facts: dict[str, Any], *, reason: str = "static_baseline") -> SelectionResult:
    rendered = render_variant(STATIC_BASELINE_VARIANT, facts)
    if not rendered:
        return SelectionResult(
            ok=False,
            variant_id=None,
            template_code=None,
            language=None,
            rendered_preview=None,
            source="rejected",
            reason="static_render_failed",
        )
    v = APPROVED_VARIANTS[STATIC_BASELINE_VARIANT]
    return SelectionResult(
        ok=True,
        variant_id=STATIC_BASELINE_VARIANT,
        template_code=v["template_code"],
        language=v["language"],
        rendered_preview=rendered,
        source="static",
        reason=reason,
    )


async def select_recovery_template_variant(
    facts: dict[str, Any],
    *,
    allow_ai: bool = False,
    fallback: FallbackMode = "static",
    model: str | None = None,
    timeout_tokens: int = 64,
) -> SelectionResult:
    """
    Select an approved variant. When allow_ai is False, always static baseline.
    AI path is bounded and validated; unsafe results never silently alter preview.
    """
    if not allow_ai:
        return select_static(facts, reason="ai_disabled")

    redacted = _redacted_facts(facts)
    allowlist = sorted(APPROVED_VARIANTS.keys())
    messages = [
        {
            "role": "system",
            "content": (
                "You select ONE recovery reminder template variant. "
                "Reply with JSON only: {\"variant_id\":\"...\"}. "
                f"variant_id must be one of: {allowlist}. "
                "Do not invent discounts, URLs, phones, amounts, or free text."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"facts": redacted, "allowlist": allowlist},
                ensure_ascii=True,
            ),
        },
    ]

    try:
        from services.llm_router import llm_chat

        raw = await llm_chat(
            messages,
            purpose="recovery_template_select",
            temperature=0.0,
            max_tokens=timeout_tokens,
            model=model,
        )
    except Exception as exc:
        logger.warning(
            "Recovery template AI selection failed",
            extra={"error_type": type(exc).__name__},
        )
        if fallback == "no_send":
            return SelectionResult(
                ok=False,
                variant_id=None,
                template_code=None,
                language=None,
                rendered_preview=None,
                source="rejected",
                reason="ai_timeout_or_error",
                model=model,
            )
        return select_static(facts, reason="ai_error_static_fallback")

    variant_id = parse_model_selection(raw if isinstance(raw, str) else "")
    if not variant_id:
        if fallback == "no_send":
            return SelectionResult(
                ok=False,
                variant_id=None,
                template_code=None,
                language=None,
                rendered_preview=None,
                source="rejected",
                reason="invalid_or_forbidden_schema",
                model=model,
            )
        return select_static(facts, reason="invalid_ai_static_fallback")

    rendered = render_variant(variant_id, facts)
    if not rendered:
        if fallback == "no_send":
            return SelectionResult(
                ok=False,
                variant_id=None,
                template_code=None,
                language=None,
                rendered_preview=None,
                source="rejected",
                reason="render_validation_failed",
                model=model,
            )
        return select_static(facts, reason="render_failed_static_fallback")

    v = APPROVED_VARIANTS[variant_id]
    return SelectionResult(
        ok=True,
        variant_id=variant_id,
        template_code=v["template_code"],
        language=v["language"],
        rendered_preview=rendered,
        source="ai",
        reason="allowlisted_variant",
        model=model,
    )

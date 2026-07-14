"""
P2.2 — Phone normalization for Indonesian numbers (pure, no DB/network).

Produces typed result, not empty string.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import re


@dataclass(frozen=True)
class PhoneNormalization:
    status: Literal["valid", "invalid", "unsupported"]
    e164: str | None
    reason: str | None


# Allowed lengths for Indonesian mobile numbers in E164 without +
# +62 8xx ... total digits after +62 typically 9-12, so full E164 12-15 chars inc +?
# We'll validate: after normalization, must be +62 followed by 9-12 digits starting with 8
# Example: +628123456789 -> valid, +628123 -> invalid too short, +6281234567890123 too long

# Characters to strip: space, dash, (), dot
_SEPARATORS_RE = re.compile(r"[ \-\(\)\.]+")

# Only digits and + allowed after stripping separators? We'll check extension, letters.

def normalize_indonesian_phone(raw: str | None) -> PhoneNormalization:
    if not raw or not isinstance(raw, str):
        return PhoneNormalization(status="invalid", e164=None, reason="recipient_missing")

    # Trim
    s = raw.strip()
    if not s:
        return PhoneNormalization(status="invalid", e164=None, reason="recipient_missing")

    # Remove common separators
    s_no_sep = _SEPARATORS_RE.sub("", s)

    # Check for extension or letters
    # If contains letters (a-zA-Z) except leading +, invalid
    if re.search(r"[a-zA-Z]", s_no_sep):
        return PhoneNormalization(status="invalid", e164=None, reason="recipient_invalid")

    # Check for extension pattern like 'x' or ';'
    if "x" in s.lower() or ";" in s:
        return PhoneNormalization(status="invalid", e164=None, reason="recipient_invalid")

    # Now s_no_sep should be like +628..., 628..., 08..., 8...
    # Remove leading +
    has_plus = s_no_sep.startswith("+")
    digits = s_no_sep[1:] if has_plus else s_no_sep

    # Must be all digits now
    if not digits.isdigit():
        return PhoneNormalization(status="invalid", e164=None, reason="recipient_invalid")

    # Length checks
    if len(digits) < 8:
        return PhoneNormalization(status="invalid", e164=None, reason="recipient_invalid")
    if len(digits) > 15:
        return PhoneNormalization(status="invalid", e164=None, reason="recipient_invalid")

    # Determine normalization
    # +62... -> keep if valid Indonesian
    if digits.startswith("62"):
        # Must be 62 + 8... and length 11-14? eg 628123456789 (12 digits) -> total 62+9-12 = 11-14
        # Check second part starts with 8
        rest = digits[2:]
        if not rest.startswith("8"):
            # Could be non-mobile Indonesian? For MVP, we treat non-8 after 62 as invalid for WA?
            # But allow if it's valid Indonesian landline? Blueprint says unsupported for other country prefix, but 62 is Indonesia
            # So if not starting 8, invalid
            return PhoneNormalization(status="invalid", e164=None, reason="recipient_invalid")
        if len(rest) < 9 or len(rest) > 12:
            return PhoneNormalization(status="invalid", e164=None, reason="recipient_invalid")
        e164 = f"+{digits}"
        return PhoneNormalization(status="valid", e164=e164, reason=None)

    if digits.startswith("0") and digits[1:].startswith("8"):
        # 08... -> +62 8...
        rest = digits[1:]  # 8...
        if len(rest) < 9 or len(rest) > 12:
            return PhoneNormalization(status="invalid", e164=None, reason="recipient_invalid")
        e164 = f"+62{rest}"
        return PhoneNormalization(status="valid", e164=e164, reason=None)

    if digits.startswith("8"):
        # 8... without leading 0 -> +62 8...
        if len(digits) < 9 or len(digits) > 12:
            return PhoneNormalization(status="invalid", e164=None, reason="recipient_invalid")
        e164 = f"+62{digits}"
        return PhoneNormalization(status="valid", e164=e164, reason=None)

    # International prefix other than +62/62/0 -> unsupported, not auto-converted to Indonesia
    # e.g., +1..., +44...
    if has_plus:
        return PhoneNormalization(status="unsupported", e164=None, reason="recipient_invalid")
    # If starts with other digits like 1..., 44..., treat as unsupported
    return PhoneNormalization(status="unsupported", e164=None, reason="recipient_invalid")

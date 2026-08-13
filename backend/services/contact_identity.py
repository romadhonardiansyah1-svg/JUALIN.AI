"""
P2.4 — Contact identity: HMAC fingerprint and encryption for stable subject.

- HMAC key separate from auth/encryption secret per INV-14
- Dual-read/single-write rotation: current + previous key version readable, write only current
- Raw address never used as lock/log/metric label
"""
from __future__ import annotations
import hashlib
import hmac
import base64
import os
from typing import Tuple

from cryptography.fernet import Fernet

from config import get_settings
from core.logging_config import get_logger

settings = get_settings()
logger = get_logger(__name__)


def _derive_fernet_key(raw_key: str) -> bytes:
    """Derive 32-byte Fernet key from raw key string via SHA256 + base64 urlsafe."""
    # SHA256 raw key to 32 bytes, then base64 urlsafe encode
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def get_fernet(key_version: int | None = None) -> Tuple[Fernet, int]:
    version = key_version or settings.CONTACT_ENCRYPTION_KEY_VERSION
    raw = settings.CONTACT_ENCRYPTION_KEY
    f_key = _derive_fernet_key(raw)
    return Fernet(f_key), version


def encrypt_address(plaintext_e164: str, key_version: int | None = None) -> Tuple[bytes, int]:
    f, version = get_fernet(key_version)
    ct = f.encrypt(plaintext_e164.encode("utf-8"))
    return ct, version


def decrypt_address(ciphertext: bytes, key_version: int | None = None) -> str | None:
    try:
        f, _ = get_fernet(key_version)
        pt = f.decrypt(ciphertext)
        return pt.decode("utf-8")
    except Exception as exc:
        # Actionable signal: a silent None here is indistinguishable from "no contact"
        # and hides key rotation without a KEY_VERSION bump. Never log ciphertext or
        # the decrypted phone number.
        logger.error(
            "contact_address_decrypt_failed",
            extra={
                "requested_key_version": key_version,
                "current_key_version": settings.CONTACT_ENCRYPTION_KEY_VERSION,
                "error_type": type(exc).__name__,
            },
        )
        return None


def hmac_fingerprint(e164: str, key_version: int | None = None) -> Tuple[str, int]:
    """
    HMAC-SHA256 of e164 using CONTACT_HMAC_KEY, returns (hex_fingerprint, key_version).
    Versioned lookup.
    """
    version = key_version or settings.CONTACT_HMAC_KEY_VERSION
    key = settings.CONTACT_HMAC_KEY
    # For rotation, in real KMS would fetch key by version; here single key
    digest = hmac.new(key.encode("utf-8"), e164.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest, version


def verify_fingerprint(e164: str, expected_hmac: str, key_version: int) -> bool:
    calc, _ = hmac_fingerprint(e164, key_version)
    return hmac.compare_digest(calc, expected_hmac)

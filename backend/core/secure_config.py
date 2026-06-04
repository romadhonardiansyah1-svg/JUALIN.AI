"""
Small encrypted JSON helper for integration credentials.
"""
import base64
import hashlib
import json
from cryptography.fernet import Fernet, InvalidToken

from config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_config(data: dict) -> str:
    payload = json.dumps(data or {}, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _fernet().encrypt(payload).decode("utf-8")


def decrypt_config(token: str) -> dict:
    if not token:
        return {}
    try:
        raw = _fernet().decrypt(token.encode("utf-8"))
        return json.loads(raw.decode("utf-8"))
    except (InvalidToken, ValueError, json.JSONDecodeError):
        return {}


def redact_config(data: dict) -> dict:
    redacted = {}
    for key, value in (data or {}).items():
        if any(word in key.lower() for word in ("token", "secret", "key", "password")):
            redacted[key] = "***" if value else ""
        else:
            redacted[key] = value
    return redacted

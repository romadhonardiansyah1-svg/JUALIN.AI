"""
P6.3 — Demo/admin Proof Mode API (hardened).

Fail-closed in production. Allowlisted scenarios only. Bounded concurrency.
No arbitrary path/DSN/command/module. Artifacts sanitized with schema version.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes_auth import get_current_user
from config import get_settings
from models.database import get_db
from models.user import User, UserRole
from services.payment_recovery.evidence_collector import (
    artifact_metadata_verification_error,
    artifact_structure_verification_error,
    backend_pass_verification_error,
    browser_pass_verification_error,
)
from services.payment_recovery.proof import (
    REQUIRED_BACKEND_SCENARIOS,
    git_source_tree_clean,
    load_sanitized_artifact,
    production_guard_blocks_proof_mode,
    run_all,
    run_scenario,
    validate_sanitized_artifact,
)
from services.payment_recovery.proof import _git_commit_sha  # evidence metadata only

router = APIRouter()
settings = get_settings()

_RUN_LOCK = threading.Lock()
_RATE_LOCK = threading.Lock()
_RATE_WINDOW_SEC = 60.0
_RATE_MAX = 6
_rate_hits: list[float] = []

SCHEMA_VERSION = "proof-artifact-v1"
_ARTIFACT_DIR = Path(__file__).resolve().parents[2] / "artifacts"
_LATEST_NAME = "proof-backend-latest.json"
_ALLOWED_NAMES = frozenset(
    {
        "proof-backend-latest.json",
        "proof-backend.json",
        "proof-browser.json",
    }
)


class ProofRunRequest(BaseModel):
    suite: str = Field(default="backend")
    seed: int = Field(default=42, ge=0, le=1_000_000)
    scenario: str | None = Field(default=None, max_length=80)

    # Explicitly reject dangerous keys if a client tries to smuggle them
    # via extra fields (Pydantic v2 ignore extras by default — forbid).
    model_config = {"extra": "forbid"}

    @field_validator("suite")
    @classmethod
    def suite_allowlist(cls, v: str) -> str:
        if v != "backend":
            raise ValueError("suite must be backend")
        return v

    @field_validator("scenario")
    @classmethod
    def scenario_chars(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not all(c.isalnum() or c in "-_" for c in v):
            raise ValueError("invalid scenario id")
        return v


def _is_production() -> bool:
    environments = {
        str(value).strip().lower()
        for value in (
            __import__("os").environ.get("ENVIRONMENT"),
            __import__("os").environ.get("APP_ENV"),
        )
        if value
    }
    return "production" in environments


def _production_proof_disabled() -> bool:
    if _is_production():
        return True
    blocked, _ = production_guard_blocks_proof_mode()
    return blocked


def _require_proof_principal(user: User) -> None:
    """Admin only, or seller when ENABLE_DEMO_PROOF_MODE (demo tenant)."""
    if _production_proof_disabled():
        raise HTTPException(status_code=404, detail="Not Found")
    if user.role == UserRole.ADMIN:
        return
    if user.role == UserRole.SELLER and getattr(settings, "ENABLE_DEMO_PROOF_MODE", False):
        return
    raise HTTPException(
        status_code=403,
        detail={
            "error": "proof_capability_forbidden",
            "message": "Proof Mode hanya untuk admin atau demo tenant",
        },
    )


def _check_rate_limit() -> None:
    now = time.monotonic()
    with _RATE_LOCK:
        global _rate_hits
        _rate_hits = [t for t in _rate_hits if now - t < _RATE_WINDOW_SEC]
        if len(_rate_hits) >= _RATE_MAX:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "proof_rate_limited",
                    "message": "Terlalu banyak permintaan Proof Mode",
                },
            )
        _rate_hits.append(now)


def _artifact_path(name: str = _LATEST_NAME) -> Path:
    if name not in _ALLOWED_NAMES:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_artifact_name", "message": "Artifact tidak diizinkan"},
        )
    # Prevent path traversal — name is basename only
    if Path(name).name != name or ".." in name or "/" in name or "\\" in name:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_artifact_name", "message": "Artifact tidak diizinkan"},
        )
    _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    return _ARTIFACT_DIR / name


def _enrich_payload(payload: dict[str, Any], *, actor_user_id: int) -> dict[str, Any]:
    payload = dict(payload)
    payload["schema_version"] = SCHEMA_VERSION
    payload["watermark"] = "DATA SIMULASI"
    payload["actor_user_id"] = actor_user_id
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    payload["environment"] = (__import__("os").environ.get("ENVIRONMENT") or "local")
    payload["redaction_status"] = "pending"
    payload["limitations"] = {
        "browser_e2e": "not_run_until_playwright",
        "staging_provider": "blocked_without_credentials",
        "live_ai": "disabled_static_baseline",
        "note": "Offline deterministic proof only. DATA SIMULASI.",
    }
    if not payload.get("commit_sha"):
        payload["commit_sha"] = _git_commit_sha()
    return payload


def _stale_status(
    data: dict[str, Any], *, expected_suite: str = "backend"
) -> str | None:
    """Return UNVERIFIED reason when evidence cannot represent current source."""
    current = _git_commit_sha()
    if current == "unknown":
        return "current_commit_unknown"
    if not git_source_tree_clean():
        return "current_source_tree_dirty"

    art_commit = data.get("commit_sha") or ""
    if not art_commit or art_commit == "unknown":
        return "missing_commit_sha"
    if art_commit != current:
        return "commit_mismatch"
    if data.get("schema_version") != SCHEMA_VERSION:
        return (
            "missing_schema_version"
            if not data.get("schema_version")
            else "schema_mismatch"
        )
    if data.get("redaction_status") != "passed":
        return "artifact_redaction_unverified"
    if data.get("suite") != expected_suite:
        return f"{expected_suite}_suite_mismatch"

    status = data.get("status")
    if status not in {
        "passed",
        "failed",
        "blocked",
        "not_run",
        "unverified",
        "UNVERIFIED",
    }:
        return "invalid_artifact_status"
    metadata_error = artifact_metadata_verification_error(
        data, expected_suite=expected_suite
    )
    if metadata_error:
        return metadata_error
    if status == "passed":
        validator = (
            backend_pass_verification_error
            if expected_suite == "backend"
            else browser_pass_verification_error
        )
        return validator(data)
    return artifact_structure_verification_error(
        data, expected_suite=expected_suite
    )


def _apply_artifact_verification(
    data: dict[str, Any], *, expected_suite: str = "backend"
) -> dict[str, Any]:
    reported_status = data.get("status")
    reason = _stale_status(data, expected_suite=expected_suite)
    if reason:
        data["verification_status"] = "UNVERIFIED"
        data["unverified_reason"] = reason
        data["status"] = "UNVERIFIED"
        if isinstance(data.get("dimensions"), dict):
            data["dimensions"] = {
                key: "unverified" if value == "passed" else value
                for key, value in data["dimensions"].items()
            }
    else:
        data["verification_status"] = reported_status or "UNVERIFIED"
    return data


def _write_sanitized_artifact(path: Path, payload: dict[str, Any]) -> None:
    """Validate first, then atomically replace the persisted artifact."""
    validate_sanitized_artifact(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            json.dump(payload, handle, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


@router.get("/capability")
async def proof_capability(current_user: User = Depends(get_current_user)):
    if _production_proof_disabled():
        raise HTTPException(status_code=404, detail="Not Found")
    blocked, reason = production_guard_blocks_proof_mode()
    allowed = (
        current_user.role == UserRole.ADMIN
        or (
            current_user.role == UserRole.SELLER
            and getattr(settings, "ENABLE_DEMO_PROOF_MODE", False)
        )
    ) and not blocked
    return {
        "available": allowed,
        "enabled": allowed,
        "blocked": blocked or _is_production(),
        "block_reason": "production_disabled" if _is_production() else (reason if blocked else None),
        "watermark": "DATA SIMULASI",
        "schema_version": SCHEMA_VERSION,
        "required_backend_scenarios": list(REQUIRED_BACKEND_SCENARIOS),
        "browser_suite": "not_run_until_playwright",
        "staging_provider": "blocked_without_credentials",
    }


@router.post("/run")
async def proof_run(
    body: ProofRunRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_proof_principal(current_user)
    _check_rate_limit()
    blocked, reason = production_guard_blocks_proof_mode()
    if blocked or _is_production():
        raise HTTPException(status_code=404, detail="Not Found")

    # Reject smuggled body keys already forbidden by pydantic; also reject query abuse
    for banned in ("dsn", "path", "command", "module", "adapter", "file", "DATABASE_URL"):
        if banned in (request.query_params or {}):
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_parameter", "message": "Parameter tidak diizinkan"},
            )

    if not _RUN_LOCK.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail={
                "error": "proof_busy",
                "message": "Proof Mode sedang berjalan; coba lagi sebentar",
            },
        )
    try:
        if body.scenario:
            if body.scenario not in REQUIRED_BACKEND_SCENARIOS:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "invalid_scenario",
                        "message": "Scenario tidak diizinkan",
                    },
                )
            one = run_scenario(body.scenario, seed=body.seed)
            payload = {
                "run_id": f"single-{body.scenario}-{body.seed}",
                "suite": "backend",
                "seed": body.seed,
                "status": one.status,
                "scenarios": [asdict(one)],
                "dimensions": {
                    "backend_invariants": one.status,
                    "browser_e2e": "not_run",
                    "staging_provider": "blocked",
                },
                "summary": {
                    "total": 1,
                    "passed": 1 if one.status == "passed" else 0,
                    "failed": 1 if one.status == "failed" else 0,
                },
                "disclaimer": "Single-scenario offline proof. DATA SIMULASI.",
            }
        else:
            payload = run_all(seed=body.seed, suite=body.suite)

        payload = _enrich_payload(payload, actor_user_id=current_user.id)
        validate_sanitized_artifact(payload)
        payload["redaction_status"] = "passed"
        payload = _apply_artifact_verification(payload)
        path = _artifact_path()
        _write_sanitized_artifact(path, payload)
        return JSONResponse(
            content=payload,
            headers={"Cache-Control": "private, no-store"},
        )
    finally:
        _RUN_LOCK.release()


def _unverified_artifact_response(
    *, reason: str, download_name: str | None = None
) -> JSONResponse:
    headers = {"Cache-Control": "private, no-store"}
    if download_name:
        headers["Content-Disposition"] = (
            f'attachment; filename="{Path(download_name).name}"'
        )
    return JSONResponse(
        content={
            "status": "UNVERIFIED",
            "verification_status": "UNVERIFIED",
            "unverified_reason": reason,
            "watermark": "DATA SIMULASI",
            "schema_version": SCHEMA_VERSION,
        },
        headers=headers,
    )


@router.get("/latest")
async def proof_latest(current_user: User = Depends(get_current_user)):
    _require_proof_principal(current_user)
    path = _artifact_path()
    if not path.is_file():
        return JSONResponse(
            status_code=404,
            content={
                "error": "proof_not_found",
                "message": "Belum ada artifact Proof Mode",
                "status": "UNVERIFIED",
                "watermark": "DATA SIMULASI",
                "schema_version": SCHEMA_VERSION,
            },
            headers={"Cache-Control": "private, no-store"},
        )
    try:
        data = load_sanitized_artifact(path)
    except ValueError:
        return _unverified_artifact_response(reason="artifact_unreadable")

    _apply_artifact_verification(data, expected_suite="backend")
    data["watermark"] = "DATA SIMULASI"
    data["schema_version"] = data.get("schema_version") or SCHEMA_VERSION
    return JSONResponse(content=data, headers={"Cache-Control": "private, no-store"})


@router.get("/download/{name}")
async def proof_download(
    name: str,
    current_user: User = Depends(get_current_user),
):
    """Authorized sanitized JSON download only for allowlisted artifact basenames."""
    _require_proof_principal(current_user)
    path = _artifact_path(name)
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail={"error": "proof_not_found", "message": "Artifact tidak ditemukan"},
        )
    try:
        data = load_sanitized_artifact(path)
    except ValueError:
        return _unverified_artifact_response(
            reason="artifact_unreadable",
            download_name=name,
        )
    expected_suite = "browser" if name == "proof-browser.json" else "backend"
    _apply_artifact_verification(data, expected_suite=expected_suite)
    data["watermark"] = "DATA SIMULASI"
    data["schema_version"] = data.get("schema_version") or SCHEMA_VERSION
    return JSONResponse(
        content=data,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="{Path(name).name}"',
        },
    )

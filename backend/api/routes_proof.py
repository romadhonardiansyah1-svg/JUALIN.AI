"""
P6.3 — Demo/admin Proof Mode API.

- No arbitrary scenario code execution
- Bounded concurrency (one in-process lock)
- Reads/writes sanitized artifacts under repo artifacts/
- Production + proof flag is fail-closed via production_guard
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes_auth import get_current_user
from config import get_settings
from models.database import get_db
from models.user import User, UserRole
from services.payment_recovery.proof import (
    REQUIRED_BACKEND_SCENARIOS,
    load_sanitized_artifact,
    production_guard_blocks_proof_mode,
    run_all,
    run_scenario,
)

router = APIRouter()
settings = get_settings()
_RUN_LOCK = threading.Lock()
_ARTIFACT_DIR = Path(__file__).resolve().parents[2] / "artifacts"
_LATEST_NAME = "proof-backend-latest.json"


class ProofRunRequest(BaseModel):
    suite: str = Field(default="backend", pattern="^(backend)$")
    seed: int = Field(default=42, ge=0, le=1_000_000)
    scenario: str | None = Field(default=None, max_length=80)


def _require_proof_principal(user: User) -> None:
    """Admin or explicit demo proof mode for authenticated sellers."""
    if user.role == UserRole.ADMIN:
        return
    if getattr(settings, "ENABLE_DEMO_PROOF_MODE", False):
        return
    raise HTTPException(
        status_code=403,
        detail={
            "error": "proof_capability_forbidden",
            "message": "Proof Mode hanya untuk admin/demo tenant",
        },
    )


def _artifact_path() -> Path:
    _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    return _ARTIFACT_DIR / _LATEST_NAME


@router.get("/capability")
async def proof_capability(current_user: User = Depends(get_current_user)):
    blocked, reason = production_guard_blocks_proof_mode()
    allowed = (
        current_user.role == UserRole.ADMIN
        or getattr(settings, "ENABLE_DEMO_PROOF_MODE", False)
    ) and not blocked
    return {
        "available": True,
        "enabled": allowed,
        "blocked": blocked,
        "block_reason": reason if blocked else None,
        "watermark": "DATA SIMULASI",
        "required_backend_scenarios": list(REQUIRED_BACKEND_SCENARIOS),
        "browser_suite": "not_run_until_playwright",
        "staging_provider": "blocked_without_credentials",
    }


@router.post("/run")
async def proof_run(
    body: ProofRunRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_proof_principal(current_user)
    blocked, reason = production_guard_blocks_proof_mode()
    if blocked:
        raise HTTPException(
            status_code=403,
            detail={"error": "proof_blocked", "message": reason},
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
            # Allowlist only
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
                "run_id": f"single-{body.scenario}",
                "suite": "backend",
                "seed": body.seed,
                "status": one.status,
                "scenarios": [asdict(one)],
                "dimensions": {
                    "backend_invariants": one.status,
                    "browser_e2e": "not_run",
                    "staging_provider": "blocked",
                },
                "disclaimer": "Single-scenario offline proof. DATA SIMULASI.",
                "watermark": "DATA SIMULASI",
                "actor_user_id": current_user.id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            payload = run_all(seed=body.seed, suite=body.suite)
            payload["watermark"] = "DATA SIMULASI"
            payload["actor_user_id"] = current_user.id

        path = _artifact_path()
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        # Redaction check
        load_sanitized_artifact(path)
        return JSONResponse(
            content=payload,
            headers={"Cache-Control": "private, no-store"},
        )
    finally:
        _RUN_LOCK.release()


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
                "watermark": "DATA SIMULASI",
            },
        )
    try:
        data = load_sanitized_artifact(path)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "redaction_failed", "message": str(exc)},
        ) from exc
    data["watermark"] = "DATA SIMULASI"
    return JSONResponse(content=data, headers={"Cache-Control": "private, no-store"})

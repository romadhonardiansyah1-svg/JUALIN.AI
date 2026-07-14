"""
P2.3 — Capability and global control endpoints.

GET /api/system/capabilities: authenticated seller, no-store, combines env → global control → tenant policy.
Admin control mutation for global kill switch.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from config import get_settings
from models.database import get_db
from models.user import User
from api.routes_auth import get_current_user
from models.agent_os import AgentPolicy
from models.payment_recovery import PaymentRecoveryControl

router = APIRouter()
settings = get_settings()


class GlobalControlUpdate(BaseModel):
    expected_version: int
    paused: Optional[bool] = None
    enabled: Optional[bool] = None
    reason: Optional[str] = ""


@router.get("/capabilities")
async def get_capabilities(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticated capabilities endpoint with Cache-Control: private, no-store.
    Combines env → global control → tenant policy.
    Never includes other tenant data.
    """
    # Env gate
    env_enabled = getattr(settings, "ENABLE_PAYMENT_RECOVERY", False)
    env_mode = getattr(settings, "PAYMENT_RECOVERY_MODE", "observe")

    # Global control
    control_result = await db.execute(select(PaymentRecoveryControl).where(PaymentRecoveryControl.id == 1))
    control = control_result.scalar_one_or_none()
    if not control:
        # No control row yet — treat as disabled/paused by default (fail-safe)
        global_enabled = False
        global_paused = True
        global_version = 0
        global_mode = env_mode
    else:
        global_enabled = control.enabled
        global_paused = control.paused
        global_version = control.version
        global_mode = env_mode  # mode from env for now, control could override later

    # Tenant policy
    policy_result = await db.execute(select(AgentPolicy).where(AgentPolicy.seller_id == current_user.id))
    policy = policy_result.scalar_one_or_none()

    if not policy:
        tenant_mode = "observe"
        tenant_paused = True
        tenant_version = 0
    else:
        tenant_mode = getattr(policy, "payment_recovery_mode", "observe") or "observe"
        tenant_paused = getattr(policy, "payment_recovery_paused", True)
        tenant_version = getattr(policy, "version", 0)

    # Combine: env is absolute upper bound, then global, then tenant
    # If env disabled, everything disabled
    # If global paused, tenant cannot enable
    # If tenant paused, disabled

    effective_enabled = env_enabled and global_enabled and not global_paused and not tenant_paused
    effective_paused = not effective_enabled or global_paused or tenant_paused
    effective_mode = tenant_mode if effective_enabled else "observe"

    # Determine reason
    reason = None
    if not env_enabled:
        reason = "feature_disabled"
    elif global_paused:
        reason = "tenant_paused" if False else "global_paused"
    elif tenant_paused:
        reason = "tenant_paused"
    elif not global_enabled:
        reason = "feature_disabled"

    # Payment recovery capability
    payment_recovery_cap = {
        "available": True,
        "enabled": effective_enabled,
        "mode": effective_mode,
        "paused": effective_paused,
        "reason": reason,
        "policy_version": tenant_version,
        "global_version": global_version,
    }

    # AI quality eval capability — check if handler exists and enabled
    ai_quality_available = getattr(settings, "ENABLE_AI_QUALITY", False)
    # For P0.5, eval returns 501, so available false until real implementation
    ai_quality_cap = {
        "available": False,
        "enabled": False,
        "reason": "not_implemented",
    }

    response_body = {
        "version": 1,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "capabilities": {
            "payment_recovery": payment_recovery_cap,
            "ai_quality_eval": ai_quality_cap,
        },
    }

    return JSONResponse(
        content=response_body,
        headers={
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
        },
    )


@router.get("/health")
async def system_health():
    """Public health without auth? No, keep simple."""
    return {"status": "ok"}


# Admin-only global control mutation
@router.put("/recovery-control")
async def update_global_control(
    body: GlobalControlUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.user import UserRole

    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")

    result = await db.execute(select(PaymentRecoveryControl).where(PaymentRecoveryControl.id == 1))
    control = result.scalar_one_or_none()

    if not control:
        control = PaymentRecoveryControl(id=1, enabled=False, paused=True, version=1, updated_by=current_user.id, reason=body.reason or "initial")
        db.add(control)
        await db.flush()
    else:
        # Optimistic concurrency
        if control.version != body.expected_version:
            raise HTTPException(status_code=409, detail={"error": "policy_stale", "message": "Data telah berubah, muat ulang."})

    if body.paused is not None:
        control.paused = bool(body.paused)
    if body.enabled is not None:
        control.enabled = bool(body.enabled)
    control.version += 1
    control.updated_by = current_user.id
    control.reason = body.reason or control.reason
    control.updated_at = datetime.now(timezone.utc)

    # Audit log
    try:
        from core.audit import record_audit
        await record_audit(
            db,
            action="admin.recovery_control.update",
            entity_type="payment_recovery_control",
            entity_id=control.id,
            actor_user_id=current_user.id,
            actor_type="admin",
            before={"version": body.expected_version},
            after={"enabled": control.enabled, "paused": control.paused, "version": control.version},
            metadata={"reason": body.reason},
        )
    except Exception:
        pass

    await db.commit()

    return {
        "id": control.id,
        "enabled": control.enabled,
        "paused": control.paused,
        "version": control.version,
        "reason": control.reason,
    }

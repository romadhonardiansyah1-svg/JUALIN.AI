"""
Template-based workflow automation endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.database import get_db
from models.user import User
from models.workflow import AutomationRule
from api.routes_auth import get_current_user

router = APIRouter()
settings = get_settings()

WORKFLOW_TEMPLATES = [
    {
        "key": "pending_payment_2h",
        "name": "Follow-up pembayaran tertunda",
        "trigger": {"type": "order_pending_for", "hours": 2},
        "action": {"type": "send_message", "template": "payment_followup"},
    },
    {
        "key": "low_stock_alert",
        "name": "Alert stok rendah",
        "trigger": {"type": "stock_below", "qty": 3},
        "action": {"type": "notify_seller", "template": "low_stock"},
    },
    {
        "key": "repeat_buyer_bundle",
        "name": "Tawarkan bundle repeat buyer",
        "trigger": {"type": "customer_tagged", "tag": "repeat_buyer"},
        "action": {"type": "suggest_bundle", "template": "repeat_buyer_bundle"},
    },
    {
        "key": "paid_processing_message",
        "name": "Pesan setelah pembayaran berhasil",
        "trigger": {"type": "order_status", "status": "paid"},
        "action": {"type": "send_message", "template": "paid_processing"},
    },
]


class RuleCreateRequest(BaseModel):
    template_key: str
    name: str | None = None
    status: str = Field(default="active", pattern="^(active|paused)$")


class RuleUpdateRequest(BaseModel):
    name: str | None = None
    status: str | None = Field(default=None, pattern="^(active|paused)$")
    is_active: bool | None = None


@router.get("/templates")
async def list_templates(current_user: User = Depends(get_current_user)):
    return WORKFLOW_TEMPLATES


@router.get("/rules")
async def list_rules(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AutomationRule)
        .where(AutomationRule.seller_id == current_user.id)
        .order_by(AutomationRule.created_at.desc())
    )
    return [
        {
            "id": r.id,
            "template_key": r.template_key,
            "name": r.name,
            "status": r.status,
            "is_active": r.status == "active",
            "trigger": r.trigger_json,
            "action": r.action_json,
        }
        for r in result.scalars().all()
    ]


@router.post("/rules")
async def create_rule(
    req: RuleCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not settings.ENABLE_WORKFLOWS:
        raise HTTPException(status_code=403, detail="Workflow automation belum diaktifkan")
    template = next((t for t in WORKFLOW_TEMPLATES if t["key"] == req.template_key), None)
    if not template:
        raise HTTPException(status_code=400, detail="Template workflow tidak dikenal")
    rule = AutomationRule(
        seller_id=current_user.id,
        template_key=template["key"],
        name=req.name or template["name"],
        status=req.status,
        trigger_json=template["trigger"],
        action_json=template["action"],
    )
    db.add(rule)
    await db.commit()
    return {"message": "Workflow rule created", "id": rule.id}


@router.patch("/rules/{rule_id}")
async def update_rule(
    rule_id: int,
    req: RuleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AutomationRule).where(AutomationRule.id == rule_id).where(AutomationRule.seller_id == current_user.id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Workflow rule tidak ditemukan")
    if req.is_active is not None:
        rule.status = "active" if req.is_active else "paused"
    elif req.status is not None:
        rule.status = req.status
    if req.name:
        rule.name = req.name
    await db.commit()
    return {"message": "Workflow rule updated", "id": rule.id, "status": rule.status}


@router.get("/runs")
async def list_runs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List automation runs for the seller."""
    from models.workflow import AutomationRun

    result = await db.execute(
        select(AutomationRun)
        .where(AutomationRun.seller_id == current_user.id)
        .order_by(AutomationRun.started_at.desc())
        .limit(50)
    )
    return [
        {
            "id": r.id,
            "rule_id": r.rule_id,
            "status": r.status,
            "context": r.context_json,
            "error_message": r.error_message,
            "started_at": r.started_at.isoformat() if r.started_at else "",
            "finished_at": r.finished_at.isoformat() if r.finished_at else "",
        }
        for r in result.scalars().all()
    ]


@router.get("/runs/{run_id}")
async def get_run_detail(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get run detail with steps."""
    from models.workflow import AutomationRun, AutomationRunStep

    result = await db.execute(
        select(AutomationRun)
        .where(AutomationRun.id == run_id)
        .where(AutomationRun.seller_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run tidak ditemukan")

    steps_result = await db.execute(
        select(AutomationRunStep)
        .where(AutomationRunStep.run_id == run.id)
        .order_by(AutomationRunStep.created_at.asc())
    )
    steps = [
        {
            "id": s.id,
            "step_type": s.step_type,
            "status": s.status,
            "input": s.input_json,
            "output": s.output_json,
            "error": s.error_message,
            "created_at": s.created_at.isoformat() if s.created_at else "",
        }
        for s in steps_result.scalars().all()
    ]

    return {
        "id": run.id,
        "rule_id": run.rule_id,
        "status": run.status,
        "context": run.context_json,
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat() if run.started_at else "",
        "finished_at": run.finished_at.isoformat() if run.finished_at else "",
        "steps": steps,
    }


"""
AI quality center endpoints.
"""
import json
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.database import get_db
from models.user import User
from models.ai_quality import AITrace, AIFeedback, AIEvalCase, AIEvalRun
from api.routes_auth import get_current_user

router = APIRouter()
settings = get_settings()
EVAL_FIXTURE_PATH = Path(__file__).resolve().parents[1] / "ai" / "evals" / "minimal_cases.json"


class FeedbackRequest(BaseModel):
    trace_id: str = ""
    rating: str = Field(pattern="^(up|down|neutral)$")
    reason: str = ""
    note: str = ""


class EvalCaseRequest(BaseModel):
    name: str
    category: str = ""
    prompt: str
    expected_behavior: str = ""


@router.get("/traces")
async def list_traces(
    status: str = "",
    min_confidence: Optional[float] = None,
    max_confidence: Optional[float] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(AITrace).where(AITrace.seller_id == current_user.id)
    if status:
        query = query.where(AITrace.status == status)
    if min_confidence is not None:
        query = query.where(AITrace.confidence >= min_confidence)
    if max_confidence is not None:
        query = query.where(AITrace.confidence <= max_confidence)
    query = query.order_by(AITrace.created_at.desc()).limit(min(limit, 200)).offset(offset)
    result = await db.execute(query)
    return [
        {
            "id": t.id,
            "trace_id": t.trace_id,
            "provider": t.provider,
            "model": t.model,
            "stage": t.stage,
            "status": t.status,
            "latency_ms": t.latency_ms,
            "confidence": t.confidence,
            "prompt_version": t.prompt_version,
            "prompt_preview": t.prompt_preview,
            "response_preview": t.response_preview,
            "error_message": t.error_message,
            "created_at": t.created_at.isoformat() if t.created_at else "",
        }
        for t in result.scalars().all()
    ]


@router.post("/feedback")
async def create_feedback(
    req: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not settings.ENABLE_AI_QUALITY:
        raise HTTPException(status_code=403, detail="AI Quality Center belum diaktifkan")
    feedback = AIFeedback(
        seller_id=current_user.id,
        trace_id=req.trace_id,
        rating=req.rating,
        reason=req.reason,
        note=req.note,
    )
    db.add(feedback)
    await db.commit()
    return {"message": "Feedback saved", "id": feedback.id}


@router.get("/eval-cases")
async def list_eval_cases(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AIEvalCase).where(AIEvalCase.is_active == 1).order_by(AIEvalCase.id.asc()))
    cases = [
        {
            "id": c.id,
            "name": c.name,
            "category": c.category,
            "prompt": c.prompt,
            "expected_behavior": c.expected_behavior,
        }
        for c in result.scalars().all()
    ]
    if cases:
        return cases
    if EVAL_FIXTURE_PATH.exists():
        return [{"id": 0, **case} for case in json.loads(EVAL_FIXTURE_PATH.read_text(encoding="utf-8"))]
    return []


@router.post("/eval-cases")
async def create_eval_case(
    req: EvalCaseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    case = AIEvalCase(
        name=req.name,
        category=req.category,
        prompt=req.prompt,
        expected_behavior=req.expected_behavior,
    )
    db.add(case)
    await db.commit()
    return {"message": "Eval case created", "id": case.id}


@router.post("/evals/run")
async def run_eval(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    P5.4 — Synchronous offline recovery variant eval (no orphan queue job).
    Full conversational AI quality suite remains unavailable until a real worker
    handler exists; this endpoint only runs deterministic recovery fixtures.
    """
    from services.payment_recovery.ai_eval import run_recovery_variant_eval

    report = run_recovery_variant_eval()
    return {
        "status": "completed",
        "mode": "offline_deterministic",
        "capability": "recovery_variant_eval",
        "seller_id": current_user.id,
        "report": report,
        "message": (
            "Eval offline selesai. Ini memvalidasi parser/allowlist recovery, "
            "bukan keunggulan model generatif."
        ),
    }


@router.get("/evals/runs/{run_id}")
async def get_eval_run(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AIEvalRun).where(AIEvalRun.id == run_id, AIEvalRun.seller_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Eval run not found")
    return {
        "id": run.id,
        "status": run.status,
        "total_cases": run.total_cases,
        "passed_cases": run.passed_cases,
        "failed_cases": run.failed_cases,
        "result_json": run.result_json,
        "created_at": run.created_at.isoformat() if run.created_at else "",
    }


# ══════════════════════════════════════════════════
# Prompt Registry
# ══════════════════════════════════════════════════

@router.get("/prompts")
async def list_prompts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.prompt_registry import PromptVersion
    result = await db.execute(
        select(PromptVersion).order_by(PromptVersion.prompt_key.asc(), PromptVersion.version.desc())
    )
    return [
        {
            "id": p.id,
            "prompt_key": p.prompt_key,
            "version": p.version,
            "content": p.content[:500],
            "description": p.description,
            "is_active": p.is_active,
            "created_at": p.created_at.isoformat() if p.created_at else "",
        }
        for p in result.scalars().all()
    ]

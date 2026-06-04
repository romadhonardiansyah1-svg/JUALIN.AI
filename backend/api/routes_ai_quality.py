"""
AI quality center endpoints.
"""
import json
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(AITrace).where(AITrace.seller_id == current_user.id)
    if status:
        query = query.where(AITrace.status == status)
    query = query.order_by(AITrace.created_at.desc()).limit(100)
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
async def run_eval_placeholder(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cases = await db.execute(select(AIEvalCase).where(AIEvalCase.is_active == 1))
    case_list = cases.scalars().all()
    run = AIEvalRun(
        seller_id=current_user.id,
        status="queued",
        total_cases=len(case_list),
        result_json={"run_id": uuid4().hex, "message": "Eval worker belum dijalankan"},
    )
    db.add(run)
    await db.commit()
    return {"message": "Eval run queued", "id": run.id, "total_cases": run.total_cases}

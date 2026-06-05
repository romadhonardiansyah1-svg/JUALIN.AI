"""
Lead capture endpoints.
Public form rate limited. Submission creates customer event.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import json
import hashlib

from models.database import get_db
from models.user import User
from models.lead import LeadForm, LeadSubmission
from api.routes_auth import get_current_user
from middleware import get_client_ip

router = APIRouter()


class LeadFormCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    slug: str = Field(min_length=3, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$")
    fields_json: list = Field(default_factory=list, max_length=30)
    success_message: str = Field(default="Terima kasih! Kami akan segera menghubungi Anda.", max_length=500)


class LeadFormSubmitData(BaseModel):
    data: dict = Field(default_factory=dict)
    submitted_at_ms: int | None = None
    honeypot: str = Field(default="", max_length=200)


def _validate_submission_data(data: dict) -> dict:
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Payload submission tidak valid")
    if len(data) > 30:
        raise HTTPException(status_code=400, detail="Terlalu banyak field submission")

    try:
        encoded = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Payload submission harus bisa disimpan sebagai JSON")

    if len(encoded) > 32 * 1024:
        raise HTTPException(status_code=413, detail="Payload submission terlalu besar")

    for key, value in data.items():
        if len(str(key)) > 100:
            raise HTTPException(status_code=400, detail="Nama field submission terlalu panjang")
        if isinstance(value, (dict, list)):
            value_text = json.dumps(value, ensure_ascii=False, default=str)
        else:
            value_text = str(value)
        if len(value_text) > 2000:
            raise HTTPException(status_code=400, detail=f"Nilai field '{key}' terlalu panjang")
    return data


def _submission_hash(data: dict) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@router.post("/")
async def create_lead_form(
    req: LeadFormCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(LeadForm).where(LeadForm.slug == req.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Slug sudah dipakai")

    form = LeadForm(
        seller_id=current_user.id,
        slug=req.slug,
        title=req.title,
        description=req.description,
        fields_json=req.fields_json or [
            {"name": "name", "type": "text", "label": "Nama", "required": True},
            {"name": "phone", "type": "tel", "label": "No. HP", "required": True},
            {"name": "message", "type": "textarea", "label": "Pesan", "required": False},
        ],
        success_message=req.success_message,
    )
    db.add(form)
    await db.commit()
    return {"id": form.id, "slug": form.slug, "message": "Lead form created"}


@router.get("/")
async def list_lead_forms(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LeadForm).where(LeadForm.seller_id == current_user.id)
        .order_by(LeadForm.created_at.desc())
    )
    return [
        {
            "id": f.id, "slug": f.slug, "title": f.title,
            "is_active": f.is_active, "submission_count": f.submission_count,
            "fields": f.fields_json,
        }
        for f in result.scalars().all()
    ]


@router.get("/submissions")
async def list_submissions(
    status: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(LeadSubmission).where(LeadSubmission.seller_id == current_user.id)
    if status:
        query = query.where(LeadSubmission.status == status)
    query = query.order_by(LeadSubmission.created_at.desc()).limit(100)
    result = await db.execute(query)
    return [
        {
            "id": s.id, "form_id": s.form_id, "data": s.data_json,
            "status": s.status, "created_at": s.created_at.isoformat() if s.created_at else "",
        }
        for s in result.scalars().all()
    ]


# ── Public endpoints ──

@router.get("/public/{slug}")
async def get_public_form(slug: str, db: AsyncSession = Depends(get_db)):
    """Public: get lead form by slug. No auth."""
    result = await db.execute(
        select(LeadForm).where(LeadForm.slug == slug, LeadForm.is_active == True)
    )
    form = result.scalar_one_or_none()
    if not form:
        raise HTTPException(status_code=404, detail="Form tidak ditemukan")

    return {
        "title": form.title,
        "description": form.description,
        "fields": form.fields_json,
        "success_message": form.success_message,
    }


@router.post("/public/{slug}/submit")
async def submit_lead_form(
    slug: str,
    req: LeadFormSubmitData,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public: submit lead form. Rate limited by IP."""
    if req.honeypot.strip():
        raise HTTPException(status_code=400, detail="Submission tidak valid")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if req.submitted_at_ms is not None:
        submitted_at = datetime.fromtimestamp(req.submitted_at_ms / 1000, tz=timezone.utc)
        elapsed_seconds = (now - submitted_at).total_seconds()
        if elapsed_seconds < 2:
            raise HTTPException(status_code=400, detail="Submission terlalu cepat")

    submission_data = _validate_submission_data(req.data)
    current_hash = _submission_hash(submission_data)
    result = await db.execute(
        select(LeadForm).where(LeadForm.slug == slug, LeadForm.is_active == True)
    )
    form = result.scalar_one_or_none()
    if not form:
        raise HTTPException(status_code=404, detail="Form tidak ditemukan")

    ip = get_client_ip(request)

    # Simple spam check: max 5 submissions per IP per form per day
    from sqlalchemy import func
    today = now.date()
    spam_check = await db.execute(
        select(func.count(LeadSubmission.id))
        .where(LeadSubmission.form_id == form.id, LeadSubmission.source_ip == ip)
        .where(func.date(LeadSubmission.created_at) == today)
    )
    if (spam_check.scalar() or 0) >= 5:
        raise HTTPException(status_code=429, detail="Terlalu banyak submission. Coba lagi besok.")

    recent_result = await db.execute(
        select(LeadSubmission)
        .where(LeadSubmission.form_id == form.id, LeadSubmission.source_ip == ip)
        .where(func.date(LeadSubmission.created_at) == today)
        .order_by(LeadSubmission.created_at.desc())
        .limit(10)
    )
    for previous in recent_result.scalars().all():
        if _submission_hash(previous.data_json or {}) == current_hash:
            raise HTTPException(status_code=409, detail="Submission yang sama sudah diterima")

    submission = LeadSubmission(
        form_id=form.id,
        seller_id=form.seller_id,
        data_json=submission_data,
        source_ip=ip,
    )
    db.add(submission)
    form.submission_count = (form.submission_count or 0) + 1
    await db.flush()

    # Create CRM customer event if phone/email provided
    try:
        from models.crm import Customer, CustomerEvent
        phone = str(submission_data.get("phone", "")).strip()
        name = str(submission_data.get("name", "Lead")).strip()[:255] or "Lead"
        if phone:
            existing_customer = await db.execute(
                select(Customer).where(Customer.seller_id == form.seller_id, Customer.phone == phone)
            )
            customer = existing_customer.scalar_one_or_none()
            if not customer:
                customer = Customer(seller_id=form.seller_id, name=name, phone=phone)
                db.add(customer)
                await db.flush()
            submission.customer_id = customer.id
            event = CustomerEvent(
                customer_id=customer.id, seller_id=form.seller_id,
                event_type="lead_form",
                title=f"Lead form submitted: {form.title}",
                data={"form_slug": slug, "submission_id": submission.id},
                source="lead_form",
            )
            db.add(event)
    except Exception:
        pass  # CRM integration best-effort

    await db.commit()
    return {"message": form.success_message}

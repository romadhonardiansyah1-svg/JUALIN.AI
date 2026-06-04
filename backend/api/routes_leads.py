"""
Lead capture endpoints.
Public form rate limited. Submission creates customer event.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from models.database import get_db
from models.user import User
from models.lead import LeadForm, LeadSubmission
from api.routes_auth import get_current_user

router = APIRouter()


class LeadFormCreate(BaseModel):
    title: str
    description: str = ""
    slug: str
    fields_json: list = []
    success_message: str = "Terima kasih! Kami akan segera menghubungi Anda."


class LeadFormSubmitData(BaseModel):
    data: dict = {}


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
    result = await db.execute(
        select(LeadForm).where(LeadForm.slug == slug, LeadForm.is_active == True)
    )
    form = result.scalar_one_or_none()
    if not form:
        raise HTTPException(status_code=404, detail="Form tidak ditemukan")

    ip = request.client.host if request.client else ""

    # Simple spam check: max 5 submissions per IP per form per day
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import func
    today = datetime.now(timezone.utc).date()
    spam_check = await db.execute(
        select(func.count(LeadSubmission.id))
        .where(LeadSubmission.form_id == form.id, LeadSubmission.source_ip == ip)
        .where(func.date(LeadSubmission.created_at) == today)
    )
    if (spam_check.scalar() or 0) >= 5:
        raise HTTPException(status_code=429, detail="Terlalu banyak submission. Coba lagi besok.")

    submission = LeadSubmission(
        form_id=form.id,
        seller_id=form.seller_id,
        data_json=req.data,
        source_ip=ip,
    )
    db.add(submission)
    form.submission_count = (form.submission_count or 0) + 1

    # Create CRM customer event if phone/email provided
    try:
        from models.crm import Customer, CustomerEvent
        phone = req.data.get("phone", "")
        name = req.data.get("name", "Lead")
        if phone:
            existing_customer = await db.execute(
                select(Customer).where(Customer.seller_id == form.seller_id, Customer.phone == phone)
            )
            customer = existing_customer.scalar_one_or_none()
            if not customer:
                customer = Customer(seller_id=form.seller_id, name=name, phone=phone, source="lead_form")
                db.add(customer)
                await db.flush()
            submission.customer_id = customer.id
            event = CustomerEvent(
                customer_id=customer.id, seller_id=form.seller_id,
                type="lead_form", data_json={"form_slug": slug, "submission_id": submission.id},
            )
            db.add(event)
    except Exception:
        pass  # CRM integration best-effort

    await db.commit()
    return {"message": form.success_message}

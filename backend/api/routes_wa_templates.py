"""
WhatsApp message template endpoints.
Seller bisa membuat, edit, dan submit templates untuk campaign di luar 24 jam.
Secret/token WhatsApp TIDAK pernah tampil di frontend.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import re

from config import get_settings
from models.database import get_db
from models.user import User
from models.wa_template import WhatsAppMessageTemplate
from api.routes_auth import get_current_user

router = APIRouter()
settings = get_settings()


class WATemplateGenerateRequest(BaseModel):
    purpose: str = "order_confirmation"  # order_confirmation, payment_reminder, promo, welcome, custom
    product_name: str = ""
    custom_prompt: str = ""


class WATemplateEditRequest(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    body: Optional[str] = None
    variables_json: Optional[list] = None


@router.post("/templates/generate")
async def generate_wa_template(
    req: WATemplateGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI-generate a WhatsApp message template draft based on purpose."""
    # Template blueprints per purpose
    blueprints = {
        "order_confirmation": {
            "name": f"order_conf_{current_user.slug}",
            "category": "utility",
            "body": "Halo {{1}}! Pesanan kamu #{{2}} sudah dikonfirmasi. Total: Rp {{3}}. Terima kasih sudah belanja di {store}! 🛒",
            "variables": [
                {"key": "1", "sample_value": "Budi", "description": "Nama customer"},
                {"key": "2", "sample_value": "ORD-001", "description": "Nomor order"},
                {"key": "3", "sample_value": "150.000", "description": "Total harga"},
            ],
        },
        "payment_reminder": {
            "name": f"payment_rem_{current_user.slug}",
            "category": "utility",
            "body": "Halo {{1}}! Pembayaran untuk pesanan #{{2}} (Rp {{3}}) belum kami terima. Yuk selesaikan pembayaran sebelum {{4}} ya. Terima kasih! 🙏",
            "variables": [
                {"key": "1", "sample_value": "Budi", "description": "Nama customer"},
                {"key": "2", "sample_value": "ORD-001", "description": "Nomor order"},
                {"key": "3", "sample_value": "150.000", "description": "Total harga"},
                {"key": "4", "sample_value": "besok jam 12:00", "description": "Deadline"},
            ],
        },
        "promo": {
            "name": f"promo_{current_user.slug}",
            "category": "marketing",
            "body": "Hai {{1}}! 🎉 Ada promo spesial dari {store}! {{2}}. Berlaku sampai {{3}}. Yuk order sekarang! 🛒",
            "variables": [
                {"key": "1", "sample_value": "Budi", "description": "Nama customer"},
                {"key": "2", "sample_value": "Diskon 20% semua produk", "description": "Detail promo"},
                {"key": "3", "sample_value": "31 Desember 2026", "description": "Masa berlaku"},
            ],
        },
        "welcome": {
            "name": f"welcome_{current_user.slug}",
            "category": "marketing",
            "body": "Halo {{1}}! 👋 Selamat datang di {store}. Terima kasih sudah menghubungi kami. Ada yang bisa kami bantu? 😊",
            "variables": [
                {"key": "1", "sample_value": "Budi", "description": "Nama customer"},
            ],
        },
    }

    bp = blueprints.get(req.purpose, blueprints["welcome"])

    # Try AI enhancement if available
    body = bp["body"].replace("{store}", current_user.nama_toko)
    try:
        if req.custom_prompt:
            from ai.llm_client import chat_completion
            resp = await chat_completion(
                messages=[
                    {"role": "system", "content": (
                        "Kamu adalah copywriter WhatsApp template. Buat template singkat, jelas, "
                        "menggunakan variabel {{1}}, {{2}}, dll. Jangan membuat klaim palsu. "
                        f"Toko: {current_user.nama_toko}."
                    )},
                    {"role": "user", "content": req.custom_prompt},
                ],
                max_tokens=200,
            )
            ai_body = resp.get("content", "") if isinstance(resp, dict) else str(resp)
            if ai_body and len(ai_body) > 10:
                body = ai_body
    except Exception:
        pass  # Use blueprint fallback

    # Create draft template
    template = WhatsAppMessageTemplate(
        seller_id=current_user.id,
        name=bp["name"],
        category=bp["category"],
        body=body,
        variables_json=bp["variables"],
        status="draft",
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)

    return {
        "id": template.id,
        "name": template.name,
        "category": template.category,
        "body": template.body,
        "variables": template.variables_json,
        "status": "draft",
    }


@router.get("/templates")
async def list_wa_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all WA templates for the current seller."""
    result = await db.execute(
        select(WhatsAppMessageTemplate)
        .where(WhatsAppMessageTemplate.seller_id == current_user.id)
        .order_by(WhatsAppMessageTemplate.created_at.desc())
    )
    templates = result.scalars().all()

    return [
        {
            "id": t.id, "name": t.name, "category": t.category,
            "language": t.language, "body": t.body,
            "variables": t.variables_json or [],
            "status": t.status,
            "rejection_reason": t.rejection_reason or "",
            "created_at": t.created_at.isoformat() if t.created_at else "",
        }
        for t in templates
    ]


@router.patch("/templates/{template_id}")
async def edit_wa_template(
    template_id: int,
    req: WATemplateEditRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Edit a WA template (only drafts can be edited)."""
    result = await db.execute(
        select(WhatsAppMessageTemplate).where(
            WhatsAppMessageTemplate.id == template_id,
            WhatsAppMessageTemplate.seller_id == current_user.id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template tidak ditemukan")

    if template.status not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail="Hanya template draft/rejected yang bisa diedit")

    if req.name is not None:
        template.name = req.name
    if req.category is not None:
        template.category = req.category
    if req.body is not None:
        template.body = req.body
    if req.variables_json is not None:
        template.variables_json = req.variables_json

    template.status = "draft"  # Reset to draft after edit
    template.rejection_reason = None

    await db.commit()
    return {"message": "Template updated", "status": "draft"}


@router.post("/templates/{template_id}/submit")
async def submit_wa_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a template for review. V1: just updates status to pending_review."""
    result = await db.execute(
        select(WhatsAppMessageTemplate).where(
            WhatsAppMessageTemplate.id == template_id,
            WhatsAppMessageTemplate.seller_id == current_user.id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template tidak ditemukan")

    if template.status not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail="Template tidak bisa disubmit dengan status ini")

    # Validate basic rules
    if not template.body or len(template.body) < 10:
        raise HTTPException(status_code=400, detail="Body template terlalu pendek (min 10 karakter)")

    template.status = "pending_review"
    await db.commit()

    return {"message": "Template submitted for review", "status": "pending_review"}


@router.post("/templates/{template_id}/sync-status")
async def sync_wa_template_status(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Sync template status from provider.
    V1: Admin can manually set status. No direct Meta API integration.
    """
    result = await db.execute(
        select(WhatsAppMessageTemplate).where(
            WhatsAppMessageTemplate.id == template_id,
            WhatsAppMessageTemplate.seller_id == current_user.id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template tidak ditemukan")

    return {
        "id": template.id,
        "status": template.status,
        "message": "Status synced (V1: manual only)",
    }

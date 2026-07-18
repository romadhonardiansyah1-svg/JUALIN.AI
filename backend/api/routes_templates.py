"""
Template marketplace endpoints.
Templates are internal curated; installed copies are seller-owned.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from config import get_settings
from models.database import get_db
from models.user import User
from models.template import Template
from api.routes_auth import get_current_user

router = APIRouter()
settings = get_settings()


class TemplateCreateRequest(BaseModel):
    type: str
    name: str
    description: str = ""
    category: str = "general"
    content_json: dict = {}
    tags: list = []


@router.get("/")
async def list_templates(
    type: Optional[str] = None,
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Template).where(Template.is_public == True)
    if type:
        query = query.where(Template.type == type)
    if category:
        query = query.where(Template.category == category)
    query = query.order_by(Template.usage_count.desc()).limit(100)

    result = await db.execute(query)
    return [
        {
            "id": t.id,
            "type": t.type,
            "name": t.name,
            "description": t.description,
            "category": t.category,
            "tags": t.tags,
            "usage_count": t.usage_count,
            "content_json": t.content_json,
        }
        for t in result.scalars().all()
    ]


@router.post("/{template_id}/install")
async def install_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Install a template by creating a seller-owned copy."""
    result = await db.execute(
        select(Template).where(
            Template.id == template_id,
            or_(Template.is_public.is_(True), Template.created_by == current_user.id),
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template tidak ditemukan")

    # Create seller copy based on type
    if template.type == "canned_reply":
        from models.inbox_extras import CannedReply
        cr = CannedReply(
            seller_id=current_user.id,
            title=template.name,
            content=template.content_json.get("content", ""),
            category=template.category,
        )
        db.add(cr)

    elif template.type == "workflow":
        from models.workflow import AutomationRule
        rule = AutomationRule(
            seller_id=current_user.id,
            template_key=template.content_json.get("template_key", ""),
            name=template.name,
            trigger_json=template.content_json.get("trigger", {}),
            action_json=template.content_json.get("action", {}),
            status="inactive",
        )
        db.add(rule)

    elif template.type == "campaign":
        from models.campaign import Campaign
        camp = Campaign(
            seller_id=current_user.id,
            title=f"[Template] {template.name}",
            content=template.content_json.get("content", ""),
            status="draft",
        )
        db.add(camp)

    # Increment usage count
    template.usage_count = (template.usage_count or 0) + 1
    await db.commit()

    return {"message": f"Template '{template.name}' installed", "type": template.type}


@router.post("/{template_id}/duplicate")
async def duplicate_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Duplicate a template as a new seller-created template."""
    result = await db.execute(
        select(Template).where(
            Template.id == template_id,
            or_(Template.is_public.is_(True), Template.created_by == current_user.id),
        )
    )
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(status_code=404, detail="Template tidak ditemukan")

    copy = Template(
        type=original.type,
        name=f"{original.name} (Copy)",
        description=original.description,
        category=original.category,
        content_json=original.content_json,
        tags=original.tags,
        is_public=False,
        created_by=current_user.id,
    )
    db.add(copy)
    await db.commit()

    return {"message": "Template duplicated", "id": copy.id}


# ── Template Niche UMKM (Market Acceptance Sprint 2) ──

@router.get("/niches")
async def list_niches(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List available template niches with template counts."""
    from sqlalchemy import func as sqlfunc

    result = await db.execute(
        select(Template.niche, sqlfunc.count(Template.id))
        .where(Template.is_public == True, Template.niche.isnot(None), Template.niche != "")
        .group_by(Template.niche)
    )
    niches = []
    niche_icons = {
        "kuliner": "🍳", "fashion": "👗", "skincare": "✨",
        "frozen_food": "🧊", "hampers": "🎁", "digital": "📱",
        "jasa": "🔧", "reseller": "📦",
    }
    niche_names = {
        "kuliner": "Kuliner Rumahan", "fashion": "Fashion",
        "skincare": "Skincare & Kosmetik", "frozen_food": "Frozen Food",
        "hampers": "Hampers & Kado", "digital": "Digital Product",
        "jasa": "Jasa Lokal", "reseller": "Reseller & Dropship",
    }
    for row in result.all():
        niche_id = row[0]
        niches.append({
            "id": niche_id,
            "name": niche_names.get(niche_id, niche_id.title()),
            "icon": niche_icons.get(niche_id, "📋"),
            "template_count": row[1],
        })

    return niches


@router.get("/recommended")
async def get_recommended_templates(
    niche: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get recommended templates for a specific niche."""
    if not niche:
        return []

    result = await db.execute(
        select(Template)
        .where(Template.is_public == True, Template.niche == niche)
        .order_by(Template.type.asc(), Template.usage_count.desc())
        .limit(50)
    )
    templates = result.scalars().all()

    # Check if pack already installed
    from models.template_install import TemplatePackInstall
    pack_id = f"niche_{niche}"
    install_result = await db.execute(
        select(TemplatePackInstall).where(
            TemplatePackInstall.seller_id == current_user.id,
            TemplatePackInstall.pack_id == pack_id,
        )
    )
    already_installed = install_result.scalar_one_or_none() is not None

    return {
        "niche": niche,
        "pack_id": pack_id,
        "already_installed": already_installed,
        "templates": [
            {
                "id": t.id, "type": t.type, "name": t.name,
                "description": t.description, "category": t.category,
                "tags": t.tags, "content_json": t.content_json,
            }
            for t in templates
        ],
    }


class InstallPackRequest(BaseModel):
    niche: str
    pack_id: str = ""


@router.post("/install-pack")
async def install_template_pack(
    req: InstallPackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Install a complete niche template pack. Idempotent per seller + pack.
    Creates seller-owned copies of all templates in the pack.
    """
    from models.template_install import TemplatePackInstall
    from models.workflow import AutomationRule
    from models.campaign import Campaign
    from models.inbox_extras import CannedReply

    pack_id = req.pack_id or f"niche_{req.niche}"

    # Check idempotency
    existing = await db.execute(
        select(TemplatePackInstall).where(
            TemplatePackInstall.seller_id == current_user.id,
            TemplatePackInstall.pack_id == pack_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"message": "Pack sudah diinstall sebelumnya", "already_installed": True}

    # Get all templates for this niche
    result = await db.execute(
        select(Template).where(
            Template.is_public == True, Template.niche == req.niche,
        )
    )
    templates = result.scalars().all()

    installed = 0
    for template in templates:
        if template.type == "canned_reply":
            cr = CannedReply(
                seller_id=current_user.id,
                title=template.name,
                content=template.content_json.get("content", ""),
                category=template.category,
            )
            db.add(cr)
        elif template.type == "workflow":
            rule = AutomationRule(
                seller_id=current_user.id,
                template_key=template.content_json.get("template_key", ""),
                name=template.name,
                trigger_json=template.content_json.get("trigger", {}),
                action_json=template.content_json.get("action", {}),
                status="inactive",
            )
            db.add(rule)
        elif template.type == "campaign":
            camp = Campaign(
                seller_id=current_user.id,
                title=f"[{req.niche.title()}] {template.name}",
                content=template.content_json.get("content", ""),
                status="draft",
            )
            db.add(camp)

        template.usage_count = (template.usage_count or 0) + 1
        installed += 1

    # Record installation
    install_record = TemplatePackInstall(
        seller_id=current_user.id,
        pack_id=pack_id,
        niche=req.niche,
    )
    db.add(install_record)
    await db.commit()

    return {
        "message": f"Pack '{req.niche}' berhasil diinstall ({installed} template)",
        "installed_count": installed,
        "already_installed": False,
    }


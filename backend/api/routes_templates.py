"""
Template marketplace endpoints.
Templates are internal curated; installed copies are seller-owned.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
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
    result = await db.execute(select(Template).where(Template.id == template_id))
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
    result = await db.execute(select(Template).where(Template.id == template_id))
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

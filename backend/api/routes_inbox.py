"""
Omnichannel inbox endpoints.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, or_
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.database import get_db
from models.user import User
from models.inbox import Channel, ChannelContact, InboxThread, InboxMessage
from api.routes_auth import get_current_user
from core.audit import record_audit
from core.secure_config import decrypt_config
from services.messaging.whatsapp_cloud import WhatsAppCloudProvider

router = APIRouter()
settings = get_settings()


class ReplyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4096)


class ModeRequest(BaseModel):
    mode: str = Field(pattern="^(ai|manual)$")


@router.get("/threads")
async def list_threads(
    q: Optional[str] = None,
    label: Optional[str] = None,
    mode: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(InboxThread, ChannelContact, Channel)
        .join(ChannelContact, InboxThread.contact_id == ChannelContact.id)
        .join(Channel, InboxThread.channel_id == Channel.id)
        .where(InboxThread.seller_id == current_user.id)
    )
    if q:
        search = f"%{q}%"
        query = query.where(
            or_(
                ChannelContact.name.ilike(search),
                ChannelContact.phone.ilike(search),
                InboxThread.last_message_preview.ilike(search),
            )
        )
    if mode:
        query = query.where(InboxThread.mode == mode)
    if label:
        from models.inbox_extras import InboxThreadLabel
        query = query.join(InboxThreadLabel, InboxThreadLabel.thread_id == InboxThread.id).where(InboxThreadLabel.label == label)

    query = query.order_by(InboxThread.last_message_at.desc().nullslast(), InboxThread.created_at.desc())
    query = query.limit(min(limit, 200)).offset(offset)

    result = await db.execute(query)
    rows = result.all()

    # Load labels for each thread
    thread_ids = [thread.id for thread, _, _ in rows]
    labels_map = {}
    if thread_ids:
        from models.inbox_extras import InboxThreadLabel
        labels_result = await db.execute(
            select(InboxThreadLabel).where(InboxThreadLabel.thread_id.in_(thread_ids))
        )
        for lbl in labels_result.scalars().all():
            labels_map.setdefault(lbl.thread_id, []).append(lbl.label)

    return [
        {
            "id": thread.id,
            "mode": thread.mode,
            "status": thread.status,
            "stage": thread.stage,
            "last_message_preview": thread.last_message_preview,
            "last_message_at": thread.last_message_at.isoformat() if thread.last_message_at else "",
            "unread_count": thread.unread_count,
            "labels": labels_map.get(thread.id, []),
            "channel": {"id": channel.id, "type": channel.type, "provider": channel.provider, "display_name": channel.display_name},
            "contact": {"id": contact.id, "name": contact.name, "phone": contact.phone},
        }
        for thread, contact, channel in rows
    ]


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InboxThread, ChannelContact, Channel)
        .join(ChannelContact, InboxThread.contact_id == ChannelContact.id)
        .join(Channel, InboxThread.channel_id == Channel.id)
        .where(InboxThread.id == thread_id)
        .where(InboxThread.seller_id == current_user.id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Thread tidak ditemukan")
    thread, contact, channel = row
    messages_result = await db.execute(
        select(InboxMessage)
        .where(InboxMessage.thread_id == thread.id)
        .where(InboxMessage.seller_id == current_user.id)
        .order_by(InboxMessage.created_at.asc())
        .limit(200)
    )
    thread.unread_count = 0
    await db.commit()
    return {
        "id": thread.id,
        "mode": thread.mode,
        "status": thread.status,
        "stage": thread.stage,
        "channel": {"id": channel.id, "type": channel.type, "provider": channel.provider, "display_name": channel.display_name},
        "contact": {"id": contact.id, "name": contact.name, "phone": contact.phone},
        "messages": [
            {
                "id": m.id,
                "direction": m.direction,
                "role": m.role,
                "content_type": m.content_type,
                "content": m.content,
                "status": m.status,
                "created_at": m.created_at.isoformat() if m.created_at else "",
            }
            for m in messages_result.scalars().all()
        ],
    }


@router.post("/threads/{thread_id}/reply")

async def reply_thread(
    thread_id: int,
    req: ReplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InboxThread, Channel, ChannelContact)
        .join(Channel, InboxThread.channel_id == Channel.id)
        .join(ChannelContact, InboxThread.contact_id == ChannelContact.id)
        .where(InboxThread.id == thread_id)
        .where(InboxThread.seller_id == current_user.id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Thread tidak ditemukan")
    thread, channel, contact = row

    if channel.provider != "whatsapp_cloud":
        raise HTTPException(
            status_code=409,
            detail="Provider channel belum mendukung balasan manual",
        )

    config = decrypt_config(channel.config_encrypted)
    provider = WhatsAppCloudProvider(
        access_token=config.get("access_token", ""),
        phone_number_id=config.get("phone_number_id", channel.external_id),
        app_secret=config.get("app_secret", ""),
    )
    provider_result = await provider.send_message(contact.phone or contact.external_id, req.text)

    message = InboxMessage(
        seller_id=current_user.id,
        thread_id=thread.id,
        direction="outbound",
        role="seller",
        content=req.text,
        status="sent" if provider_result.success else "failed",
        external_message_id=provider_result.provider_message_id,
        raw_payload=provider_result.raw,
    )
    db.add(message)
    thread.last_message_preview = req.text[:500]
    thread.last_message_at = datetime.now(timezone.utc)
    thread.mode = "manual"
    await record_audit(
        db,
        action="inbox.manual_reply",
        entity_type="inbox_thread",
        entity_id=thread.id,
        seller_id=current_user.id,
        actor_user_id=current_user.id,
        actor_type="seller",
        after={"message_id": message.external_message_id, "status": message.status},
    )
    await db.commit()
    if not provider_result.success:
        raise HTTPException(status_code=502, detail=provider_result.error_message)
    return {"message": "Reply sent", "thread_id": thread.id, "mode": thread.mode}


@router.patch("/threads/{thread_id}/mode")
async def update_thread_mode(
    thread_id: int,
    req: ModeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InboxThread)
        .where(InboxThread.id == thread_id)
        .where(InboxThread.seller_id == current_user.id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread tidak ditemukan")
    before = {"mode": thread.mode}
    thread.mode = req.mode
    await record_audit(
        db,
        action="inbox.mode_changed",
        entity_type="inbox_thread",
        entity_id=thread.id,
        seller_id=current_user.id,
        actor_user_id=current_user.id,
        actor_type="seller",
        before=before,
        after={"mode": req.mode},
    )
    await db.commit()
    return {"thread_id": thread.id, "mode": thread.mode}


class FeedbackRequest(BaseModel):
    rating: str = Field(pattern="^(up|down|neutral)$")
    reason: str = Field(default="", max_length=100)
    note: str = Field(default="", max_length=1000)


class AssignCustomerRequest(BaseModel):
    customer_id: int = Field(gt=0)


@router.patch("/messages/{message_id}/feedback")
async def submit_feedback(
    message_id: int,
    req: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit feedback on an AI-generated inbox message."""
    from models.ai_quality import AIFeedback

    # Verify message belongs to seller
    result = await db.execute(
        select(InboxMessage)
        .where(InboxMessage.id == message_id)
        .where(InboxMessage.seller_id == current_user.id)
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message tidak ditemukan")
    if message.role != "ai":
        raise HTTPException(status_code=400, detail="Feedback hanya untuk pesan AI")

    feedback = AIFeedback(
        seller_id=current_user.id,
        message_id=message_id,
        rating=req.rating,
        reason=req.reason,
        note=req.note,
    )
    db.add(feedback)
    await db.commit()
    return {"message": "Feedback disimpan", "feedback_id": feedback.id}


@router.post("/threads/{thread_id}/assign-customer")
async def assign_customer(
    thread_id: int,
    req: AssignCustomerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Link a CRM customer to an inbox thread."""
    from models.crm import Customer

    result = await db.execute(
        select(InboxThread)
        .where(InboxThread.id == thread_id)
        .where(InboxThread.seller_id == current_user.id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread tidak ditemukan")

    cust_result = await db.execute(
        select(Customer)
        .where(Customer.id == req.customer_id)
        .where(Customer.seller_id == current_user.id)
    )
    customer = cust_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")

    thread.customer_id = req.customer_id
    await record_audit(
        db,
        action="inbox.assign_customer",
        entity_type="inbox_thread",
        entity_id=thread.id,
        seller_id=current_user.id,
        actor_user_id=current_user.id,
        actor_type="seller",
        after={"customer_id": req.customer_id},
    )
    await db.commit()
    return {"message": "Customer assigned", "thread_id": thread.id, "customer_id": req.customer_id}


# ══════════════════════════════════════════════════
# Labels
# ══════════════════════════════════════════════════

class LabelRequest(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    action: str = Field(default="add", pattern="^(add|remove)$")


@router.post("/threads/{thread_id}/labels")
async def manage_thread_label(
    thread_id: int,
    req: LabelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.inbox_extras import InboxThreadLabel

    thread = await _get_thread(db, thread_id, current_user.id)

    if req.action == "add":
        existing = await db.execute(
            select(InboxThreadLabel)
            .where(InboxThreadLabel.thread_id == thread.id, InboxThreadLabel.label == req.label)
        )
        if existing.scalar_one_or_none():
            return {"message": "Label already exists"}
        db.add(InboxThreadLabel(seller_id=current_user.id, thread_id=thread.id, label=req.label))
    else:
        existing = await db.execute(
            select(InboxThreadLabel)
            .where(InboxThreadLabel.thread_id == thread.id, InboxThreadLabel.label == req.label)
        )
        lbl = existing.scalar_one_or_none()
        if lbl:
            await db.delete(lbl)

    await db.commit()
    return {"message": f"Label '{req.label}' {req.action}ed", "thread_id": thread.id}


# ══════════════════════════════════════════════════
# Internal Notes
# ══════════════════════════════════════════════════

class NoteRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


@router.post("/threads/{thread_id}/notes")
async def add_internal_note(
    thread_id: int,
    req: NoteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.inbox_extras import InboxInternalNote

    thread = await _get_thread(db, thread_id, current_user.id)
    note = InboxInternalNote(
        seller_id=current_user.id,
        thread_id=thread.id,
        user_id=current_user.id,
        content=req.content,
    )
    db.add(note)
    await db.commit()
    return {"message": "Note added", "note_id": note.id}


@router.get("/threads/{thread_id}/notes")
async def list_thread_notes(
    thread_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.inbox_extras import InboxInternalNote

    thread = await _get_thread(db, thread_id, current_user.id)
    result = await db.execute(
        select(InboxInternalNote)
        .where(InboxInternalNote.thread_id == thread.id)
        .order_by(InboxInternalNote.created_at.desc())
        .limit(50)
    )
    return [
        {
            "id": n.id,
            "content": n.content,
            "user_id": n.user_id,
            "created_at": n.created_at.isoformat() if n.created_at else "",
        }
        for n in result.scalars().all()
    ]


# ══════════════════════════════════════════════════
# Canned Replies
# ══════════════════════════════════════════════════

class CannedReplyRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=4096)
    category: str = Field(default="general", max_length=100)


@router.get("/canned-replies")
async def list_canned_replies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.inbox_extras import CannedReply

    result = await db.execute(
        select(CannedReply)
        .where(CannedReply.seller_id == current_user.id)
        .order_by(CannedReply.usage_count.desc())
    )
    return [
        {
            "id": cr.id,
            "title": cr.title,
            "content": cr.content,
            "category": cr.category,
            "usage_count": cr.usage_count,
        }
        for cr in result.scalars().all()
    ]


@router.post("/canned-replies")
async def create_canned_reply(
    req: CannedReplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from models.inbox_extras import CannedReply

    cr = CannedReply(
        seller_id=current_user.id,
        title=req.title,
        content=req.content,
        category=req.category,
    )
    db.add(cr)
    await db.commit()
    return {"id": cr.id, "title": cr.title, "content": cr.content}


# ── Helper ──

async def _get_thread(db: AsyncSession, thread_id: int, seller_id: int) -> InboxThread:
    result = await db.execute(
        select(InboxThread)
        .where(InboxThread.id == thread_id, InboxThread.seller_id == seller_id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread tidak ditemukan")
    return thread

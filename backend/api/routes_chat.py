"""
JUALIN.AI — Chat API Routes  
Send message → AI response → save to DB
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
import uuid

from config import get_settings
from models.database import get_db
from models.user import User, UserTier
from models.conversation import Conversation, Message, MessageRole
from api.routes_auth import get_current_user

router = APIRouter()
settings = get_settings()


# ── Pydantic Schemas ──

class ChatSendRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    seller_slug: str  # Which store to chat with


class ChatResponse(BaseModel):
    response: str
    session_id: str
    quota_exceeded: bool = False
    conversation_id: int = 0


class ConversationResponse(BaseModel):
    id: int
    session_id: str
    customer_name: str
    is_urgent: int
    message_count: int = 0
    last_message: str = ""
    created_at: str


# ── Helpers ──

async def check_quota(seller_id: int, db: AsyncSession) -> dict:
    """Check seller's chat quota for current month."""
    result = await db.execute(
        select(func.count(Conversation.id))
        .where(Conversation.seller_id == seller_id)
        .where(
            func.date_trunc("month", Conversation.created_at) == 
            func.date_trunc("month", func.now())
        )
    )
    used = result.scalar() or 0
    
    # Get seller tier
    seller_result = await db.execute(select(User).where(User.id == seller_id))
    seller = seller_result.scalar_one()
    
    limits = {
        UserTier.FREE: settings.QUOTA_FREE,
        UserTier.STARTER: settings.QUOTA_STARTER,
        UserTier.PRO: settings.QUOTA_PRO,
        UserTier.BISNIS: settings.QUOTA_BISNIS,
    }
    limit = limits.get(seller.tier, 50)
    
    return {
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "is_exceeded": used >= limit,
        "percentage": round(used / limit * 100) if limit > 0 else 100,
    }


# ── Endpoints ──

@router.post("/send", response_model=ChatResponse)
async def send_message(
    req: ChatSendRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Customer sends a message → AI processes → returns response.
    Public endpoint (no auth needed — customers don't have accounts).
    """
    # Find seller by slug
    result = await db.execute(select(User).where(User.slug == req.seller_slug))
    seller = result.scalar_one_or_none()
    
    if not seller:
        raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
    
    if not seller.ai_active:
        return ChatResponse(
            response="Maaf, toko ini sedang tidak aktif. Silakan coba lagi nanti ya 🙏",
            session_id=req.session_id or str(uuid.uuid4()),
            quota_exceeded=False,
        )
    
    # Check quota
    quota = await check_quota(seller.id, db)
    if quota["is_exceeded"]:
        return ChatResponse(
            response=f"Hai kak! Terima kasih sudah menghubungi {seller.nama_toko} 😊\n"
                     f"Saat ini penjual kami sedang tidak tersedia.\n"
                     f"Silakan hubungi langsung via {seller.no_hp or 'kontak toko'} ya kak! 🙏",
            session_id=req.session_id or str(uuid.uuid4()),
            quota_exceeded=True,
        )
    
    # Get or create conversation
    session_id = req.session_id or str(uuid.uuid4())
    
    result = await db.execute(
        select(Conversation)
        .where(Conversation.session_id == session_id)
        .where(Conversation.seller_id == seller.id)
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        conversation = Conversation(
            seller_id=seller.id,
            session_id=session_id,
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
    
    # Customer Memory — cek apakah returning customer
    memory_context = ""
    try:
        from services.customer_memory import get_or_create_memory, format_memory_context
        memory, is_returning = await get_or_create_memory(
            seller_id=seller.id,
            session_id=session_id,
            db=db,
            phone=conversation.customer_phone or "",
            name=conversation.customer_name or "Customer",
        )
        memory_context = format_memory_context(memory, is_returning)
    except Exception as e:
        print(f"⚠️ Memory lookup skipped: {e}")
    
    # Save customer message
    customer_msg = Message(
        conversation_id=conversation.id,
        role=MessageRole.CUSTOMER,
        content=req.message,
    )
    db.add(customer_msg)
    await db.commit()
    
    # Get chat history for context
    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(10)  # Last 10 messages for context
    )
    history = list(reversed(history_result.scalars().all()))
    
    # Generate AI response (with memory context injected)
    try:
        from ai.agent import get_ai_response
        ai_response_text = await get_ai_response(
            message=req.message,
            seller_id=seller.id,
            conversation_history=history,
            seller_style=seller.ai_style,
            db=db,
            memory_context=memory_context,
        )
    except Exception as e:
        print(f"❌ AI Error: {e}")
        ai_response_text = (
            f"Hai kak! Terima kasih sudah menghubungi {seller.nama_toko} 😊\n"
            f"Maaf, asisten kami sedang sibuk. Coba kirim pesan lagi ya kak!"
        )
    
    # Save AI response
    ai_msg = Message(
        conversation_id=conversation.id,
        role=MessageRole.AI,
        content=ai_response_text,
    )
    db.add(ai_msg)
    await db.commit()
    
    return ChatResponse(
        response=ai_response_text,
        session_id=session_id,
        conversation_id=conversation.id,
    )


@router.get("/history/{session_id}")
async def get_chat_history(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all messages in a conversation."""
    result = await db.execute(
        select(Conversation).where(Conversation.session_id == session_id)
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    messages_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at)
    )
    messages = messages_result.scalars().all()
    
    return {
        "session_id": session_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role.value,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else "",
            }
            for m in messages
        ]
    }


@router.get("/conversations")
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all conversations for the current seller."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.seller_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(50)
    )
    conversations = result.scalars().all()
    
    response = []
    for conv in conversations:
        # Get last message
        last_msg_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        last_msg = last_msg_result.scalar_one_or_none()
        
        # Count messages
        count_result = await db.execute(
            select(func.count(Message.id))
            .where(Message.conversation_id == conv.id)
        )
        msg_count = count_result.scalar() or 0
        
        response.append({
            "id": conv.id,
            "session_id": conv.session_id,
            "customer_name": conv.customer_name,
            "is_urgent": conv.is_urgent,
            "message_count": msg_count,
            "last_message": last_msg.content[:100] if last_msg else "",
            "created_at": conv.created_at.isoformat() if conv.created_at else "",
        })
    
    return response


@router.get("/quota")
async def get_quota(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current seller's quota usage."""
    return await check_quota(current_user.id, db)

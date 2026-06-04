"""
JUALIN.AI — Streaming Chat API (SSE)
Server-Sent Events endpoint for real-time token-by-token AI responses.

Protocol:
    POST /api/chat/stream
    Content-Type: application/json
    Response: text/event-stream

    Events:
    data: {"type":"metadata","intent":"product","stage":"discovery"}\n\n
    data: {"type":"token","token":"Hai "}\n\n
    data: {"type":"token","token":"kak!"}\n\n
    data: {"type":"done","full_response":"Hai kak!","intent":"product","stage":"discovery"}\n\n
"""
import json
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional

from config import get_settings
from models.database import get_db
from models.user import User, UserTier
from models.conversation import Conversation, Message, MessageRole
from models.chat_analytics import ChatAnalytics
from core.logging_config import get_logger

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)


class StreamChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    seller_slug: str


async def _check_quota_simple(seller_id: int, db: AsyncSession) -> tuple[bool, int, int]:
    """Quick quota check. Returns (is_exceeded, used, limit)."""
    result = await db.execute(
        select(func.count(Conversation.id))
        .where(Conversation.seller_id == seller_id)
        .where(
            func.date_trunc("month", Conversation.created_at) ==
            func.date_trunc("month", func.now())
        )
    )
    used = result.scalar() or 0

    seller_result = await db.execute(select(User).where(User.id == seller_id))
    seller = seller_result.scalar_one()

    limits = {
        UserTier.FREE: settings.QUOTA_FREE,
        UserTier.STARTER: settings.QUOTA_STARTER,
        UserTier.PRO: settings.QUOTA_PRO,
        UserTier.BISNIS: settings.QUOTA_BISNIS,
    }
    limit = limits.get(seller.tier, 50)
    return used >= limit, used, limit


async def _sse_event(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def stream_chat(
    req: StreamChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    SSE streaming chat endpoint.
    Customer sends message → AI streams response token-by-token.
    Public endpoint (no auth needed).
    """
    start_time = time.monotonic()

    # Find seller
    result = await db.execute(select(User).where(User.slug == req.seller_slug))
    seller = result.scalar_one_or_none()

    if not seller:
        raise HTTPException(status_code=404, detail="Toko tidak ditemukan")

    if not seller.ai_active:
        async def inactive_stream():
            yield await _sse_event({
                "type": "token",
                "token": "Maaf, toko ini sedang tidak aktif. Silakan coba lagi nanti ya 🙏",
            })
            yield await _sse_event({"type": "done", "done": True})
        return StreamingResponse(inactive_stream(), media_type="text/event-stream")

    # Check quota
    is_exceeded, _, _ = await _check_quota_simple(seller.id, db)
    if is_exceeded:
        async def quota_stream():
            msg = (
                f"Hai kak! Terima kasih sudah menghubungi {seller.nama_toko} 😊\n"
                f"Saat ini penjual kami sedang tidak tersedia.\n"
                f"Silakan hubungi langsung via {seller.no_hp or 'kontak toko'} ya kak! 🙏"
            )
            yield await _sse_event({"type": "token", "token": msg})
            yield await _sse_event({"type": "done", "done": True, "quota_exceeded": True})
        return StreamingResponse(quota_stream(), media_type="text/event-stream")

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

    # Save customer message
    customer_msg = Message(
        conversation_id=conversation.id,
        role=MessageRole.CUSTOMER,
        content=req.message,
    )
    db.add(customer_msg)
    await db.commit()

    # Load history
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(6)
    )
    history = list(reversed(result.scalars().all()))

    # Memory context
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
        logger.warning(f"Memory lookup skipped in stream: {e}")

    # Build streaming response
    from ai.agent import get_ai_response_stream

    # Capture variables for the generator closure
    conv_id = conversation.id
    seller_id = seller.id

    async def generate_stream():
        """
        Async generator that yields SSE events.
        After streaming, saves AI response and analytics to DB.
        """
        full_response = ""
        intent = "general"
        sales_stage = "greeting"
        duration_ms = 0

        try:
            async for chunk in get_ai_response_stream(
                message=req.message,
                seller_id=seller_id,
                conversation_history=history,
                seller_style=seller.ai_style,
                db=db,
                memory_context=memory_context,
            ):
                if chunk["type"] == "metadata":
                    intent = chunk.get("intent", "general")
                    sales_stage = chunk.get("stage", "greeting")
                    yield await _sse_event(chunk)

                elif chunk["type"] == "token":
                    full_response += chunk["token"]
                    yield await _sse_event(chunk)

                elif chunk["type"] == "done":
                    full_response = chunk.get("full_response", full_response)
                    intent = chunk.get("intent", intent)
                    sales_stage = chunk.get("stage", sales_stage)
                    duration_ms = chunk.get("duration_ms", 0)
                    yield await _sse_event({
                        "type": "done",
                        "done": True,
                        "full_response": full_response,
                        "intent": intent,
                        "stage": sales_stage,
                        "session_id": session_id,
                    })

        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            fallback = "Maaf kak, terjadi gangguan. Coba kirim lagi ya 🙏"
            full_response = fallback
            yield await _sse_event({"type": "token", "token": fallback})
            yield await _sse_event({"type": "done", "done": True})

        # Save AI response to DB (after stream completes)
        try:
            ai_msg = Message(
                conversation_id=conv_id,
                role=MessageRole.AI,
                content=full_response,
            )
            db.add(ai_msg)

            # Save analytics
            analytics = ChatAnalytics(
                conversation_id=conv_id,
                seller_id=seller_id,
                intent=intent,
                sales_stage=sales_stage,
                response_time_ms=duration_ms,
                user_message_length=len(req.message),
                ai_response_length=len(full_response),
                converted_to_order="ORDER CONFIRMED" in full_response.upper(),
            )
            db.add(analytics)

            await db.commit()
        except Exception as e:
            logger.error(f"Failed to save stream response to DB: {e}", exc_info=True)

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )

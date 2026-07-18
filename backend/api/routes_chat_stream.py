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
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
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
    message: str = Field(min_length=1, max_length=4000)
    session_id: Optional[str] = Field(default=None, max_length=255)
    seller_slug: str = Field(min_length=1, max_length=255)


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
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    SSE streaming chat endpoint.
    Customer sends message → AI streams response token-by-token.
    Public endpoint (no auth needed).
    """
    start_time = time.monotonic()

    # Rate limit (endpoint publik!)
    from core.rate_limit import check_rate_limit
    client_ip = request.client.host if request.client else "unknown"
    rl = await check_rate_limit(f"chat:{client_ip}",
                                max_requests=settings.CHAT_RATE_LIMIT_PER_MIN, window_seconds=60)
    if not rl["allowed"]:
        raise HTTPException(status_code=429, detail="Terlalu banyak permintaan. Coba lagi nanti.")

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
        .limit(10)
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

    # ── JUALIN OS: konteks deal + Negotiator ambil alih giliran nego (JALUR DEMO UTAMA) ──
    if settings.ENABLE_AGENT_OS:
        try:
            from services.agent_os.negotiation import get_deal_context
            memory_context += await get_deal_context(seller.id, conversation.id, db)
        except Exception as e:
            logger.warning(f"deal context skipped in stream: {e}")

        os_result = {"handled": False}
        try:
            from services.agent_os.orchestrator import agent_os_handle_turn
            os_result = await agent_os_handle_turn(
                seller=seller, conversation=conversation, message=req.message,
                history=history, db=db, memory_context=memory_context,
            )
        except Exception as e:
            logger.warning(f"Agent OS stream turn skipped: {e}")

        if os_result.get("handled"):
            reply_text = os_result["reply"]
            nego_meta = os_result.get("nego") or {}
            conv_id_nego = conversation.id
            seller_id_nego = seller.id

            async def nego_stream():
                yield await _sse_event({
                    "type": "metadata",
                    "intent": os_result.get("intent", "order"),
                    "stage": os_result.get("stage", "negotiation"),
                })
                for word in reply_text.split(" "):
                    yield await _sse_event({"type": "token", "token": word + " "})
                yield await _sse_event({"type": "nego", **nego_meta})

                try:
                    db.add(Message(
                        conversation_id=conv_id_nego,
                        role=MessageRole.AI,
                        content=reply_text,
                    ))
                    db.add(ChatAnalytics(
                        conversation_id=conv_id_nego,
                        seller_id=seller_id_nego,
                        intent=os_result.get("intent", "order"),
                        sales_stage=os_result.get("stage", "negotiation"),
                        response_time_ms=round((time.monotonic() - start_time) * 1000),
                        user_message_length=len(req.message),
                        ai_response_length=len(reply_text),
                        converted_to_order=False,
                    ))
                    await db.commit()
                except Exception as exc:
                    await db.rollback()
                    logger.error(
                        f"Failed to save nego stream response: {exc}",
                        exc_info=True,
                    )
                    yield await _sse_event({
                        "type": "error",
                        "error": "response_persistence_failed",
                        "message": "Respons belum tersimpan. Periksa riwayat chat sebelum mencoba lagi.",
                    })
                    return

                yield await _sse_event({
                    "type": "done",
                    "done": True,
                    "full_response": reply_text,
                    "intent": os_result.get("intent", "order"),
                    "stage": os_result.get("stage", "negotiation"),
                    "session_id": session_id,
                })

            return StreamingResponse(
                nego_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

    # Build streaming response
    from ai.agent import get_ai_response_stream

    # Capture variables for the generator closure
    conv_id = conversation.id
    seller_id = seller.id

    async def generate_stream():
        """Stream tokens, but acknowledge completion only after durable persistence."""
        full_response = ""
        intent = "general"
        sales_stage = "greeting"
        duration_ms = 0
        order_created = False

        async def persist_response():
            db.add(Message(
                conversation_id=conv_id,
                role=MessageRole.AI,
                content=full_response,
            ))
            db.add(ChatAnalytics(
                conversation_id=conv_id,
                seller_id=seller_id,
                intent=intent,
                sales_stage=sales_stage,
                response_time_ms=duration_ms,
                user_message_length=len(req.message),
                ai_response_length=len(full_response),
                converted_to_order=order_created,
            ))
            await db.commit()

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
                    continue

                if chunk["type"] == "token":
                    full_response += chunk["token"]
                    yield await _sse_event(chunk)
                    continue

                if chunk["type"] != "done":
                    continue

                full_response = chunk.get("full_response", full_response)
                intent = chunk.get("intent", intent)
                sales_stage = chunk.get("stage", sales_stage)
                duration_ms = chunk.get("duration_ms", 0)

                try:
                    from api.routes_chat import maybe_create_order_from_ai_response
                    updated_response, order_created = await maybe_create_order_from_ai_response(
                        ai_response_text=full_response,
                        seller=seller,
                        conversation=conversation,
                        session_id=session_id,
                        db=db,
                    )
                    if updated_response != full_response:
                        appended = (
                            updated_response[len(full_response):]
                            if updated_response.startswith(full_response)
                            else updated_response
                        )
                        full_response = updated_response
                        if appended:
                            yield await _sse_event({"type": "token", "token": appended})
                except Exception as exc:
                    logger.error(f"Stream order creation failed: {exc}", exc_info=True)

                try:
                    await persist_response()
                except Exception as exc:
                    await db.rollback()
                    logger.error(
                        f"Failed to save stream response to DB: {exc}",
                        exc_info=True,
                    )
                    yield await _sse_event({
                        "type": "error",
                        "error": "response_persistence_failed",
                        "message": "Respons belum tersimpan. Periksa riwayat chat sebelum mencoba lagi.",
                    })
                    return

                yield await _sse_event({
                    "type": "done",
                    "done": True,
                    "full_response": full_response,
                    "intent": intent,
                    "stage": sales_stage,
                    "session_id": session_id,
                })
                return

            raise RuntimeError("AI stream ended without completion event")

        except Exception as exc:
            logger.error(f"Stream error: {exc}", exc_info=True)
            fallback = "Maaf kak, terjadi gangguan. Jangan kirim ulang dulu; periksa riwayat chat ya 🙏"
            full_response += fallback
            yield await _sse_event({"type": "token", "token": fallback})

            try:
                await persist_response()
            except Exception as persist_exc:
                await db.rollback()
                logger.error(
                    f"Failed to save degraded stream response: {persist_exc}",
                    exc_info=True,
                )
                yield await _sse_event({
                    "type": "error",
                    "error": "response_persistence_failed",
                    "message": "Respons belum tersimpan. Periksa riwayat chat sebelum mencoba lagi.",
                })
                return

            yield await _sse_event({
                "type": "done",
                "done": True,
                "degraded": True,
                "full_response": full_response,
                "intent": intent,
                "stage": sales_stage,
                "session_id": session_id,
            })

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )

"""
JUALIN.AI — Chat API Routes  
Send message → AI response → save to DB
Optimized: sequential safe DB calls, reduced context
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
import uuid
import re
import time

from config import get_settings
from models.database import get_db
from models.user import User, UserTier
from models.conversation import Conversation, Message, MessageRole
from models.chat_analytics import ChatAnalytics
from api.routes_auth import get_current_user
from core.logging_config import get_logger

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)


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

def parse_product_line(line: str) -> tuple[str, int]:
    # e.g., "Baju Pink Satin x2" or "Baju Pink Satin x 2" or "Baju Pink Satin 2pcs" or "Baju Pink Satin (2 pcs)"
    qty_match = re.search(r'\s+x\s*(\d+)\b', line, re.IGNORECASE)
    if not qty_match:
        qty_match = re.search(r'\b(\d+)\s*pcs\b', line, re.IGNORECASE)
    if not qty_match:
        qty_match = re.search(r'\s+(\d+)$', line) # quantity at the end of line
        
    if qty_match:
        qty = int(qty_match.group(1))
        # remove quantity pattern from line to get the clean product name
        clean_name = line.replace(qty_match.group(0), "").strip()
        return clean_name, qty
    else:
        return line.strip(), 1


def parse_order_text(text: str) -> dict | None:
    # check if "ORDER CONFIRMED" is in text
    if "ORDER CONFIRMED" not in text:
        return None
    
    # regex extract fields
    nama_match = re.search(r'(?:Nama|Name)\s*:\s*(.+)', text, re.IGNORECASE)
    alamat_match = re.search(r'(?:Alamat|Address)\s*:\s*(.+)', text, re.IGNORECASE)
    hp_match = re.search(r'(?:HP|No HP|Phone|Telepon)\s*:\s*(.+)', text, re.IGNORECASE)
    
    if not (nama_match and alamat_match and hp_match):
        return None
        
    # extract products
    products_raw = []
    lines = text.split('\n')
    for line in lines:
        p_match = re.search(r'(?:Produk|Product)\s*:\s*(.+)', line, re.IGNORECASE)
        if p_match:
            products_raw.append(p_match.group(1).strip())
            
    if not products_raw:
        return None
        
    return {
        "customer_name": nama_match.group(1).strip(),
        "customer_address": alamat_match.group(1).strip(),
        "customer_phone": hp_match.group(1).strip(),
        "products_raw": products_raw
    }


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
    
    # Save customer message first
    customer_msg = Message(
        conversation_id=conversation.id,
        role=MessageRole.CUSTOMER,
        content=req.message,
    )
    db.add(customer_msg)
    await db.commit()
    
    # Load history + memory sequentially (AsyncSession is NOT safe for concurrent use)
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(6)  # Reduced from 10 for faster AI response
    )
    history = list(reversed(result.scalars().all()))
    
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
        logger.warning(f"Memory lookup skipped: {e}")
    
    # Generate AI response (with memory context injected)
    intent = "general"
    sales_stage = "greeting"
    response_start = time.monotonic()
    try:
        from ai.agent import get_ai_response
        ai_response_text, intent, sales_stage = await get_ai_response(
            message=req.message,
            seller_id=seller.id,
            conversation_history=history,
            seller_style=seller.ai_style,
            db=db,
            memory_context=memory_context,
        )
    except Exception as e:
        logger.error(f"AI Error: {e}", exc_info=True)
        ai_response_text = (
            f"Hai kak! Terima kasih sudah menghubungi {seller.nama_toko} 😊\n"
            f"Maaf, asisten kami sedang sibuk. Coba kirim pesan lagi ya kak!"
        )
    response_time_ms = round((time.monotonic() - response_start) * 1000)
    
    # Parse and create order if AI confirmed the order
    parsed = parse_order_text(ai_response_text)
    if parsed:
        try:
            # 1. Update conversation customer info
            conversation.customer_name = parsed["customer_name"]
            conversation.customer_phone = parsed["customer_phone"]
            db.add(conversation)
            await db.commit()

            # 2. Match products in database to get correct IDs & prices
            from models.product import Product
            prod_result = await db.execute(
                select(Product)
                .where(Product.seller_id == seller.id)
                .where(Product.is_active == 1)
            )
            all_seller_products = prod_result.scalars().all()

            items = []
            for raw_p in parsed["products_raw"]:
                clean_name, qty = parse_product_line(raw_p)
                matched_prod = None
                # pass 1: exact match
                for p in all_seller_products:
                    if p.nama.lower().strip() == clean_name.lower():
                        matched_prod = p
                        break
                # pass 2: substring match
                if not matched_prod:
                    for p in all_seller_products:
                        if clean_name.lower() in p.nama.lower() or p.nama.lower() in clean_name.lower():
                            matched_prod = p
                            break
                
                if matched_prod:
                    items.append({
                        "product_id": matched_prod.id,
                        "nama": matched_prod.nama,
                        "qty": qty,
                        "harga": matched_prod.harga
                    })
            
            if items:
                from ai.tools import tool_buat_order
                # create order in database & reduce stock
                order_result = await tool_buat_order(
                    seller_id=seller.id,
                    customer_name=parsed["customer_name"],
                    customer_phone=parsed["customer_phone"],
                    customer_address=parsed["customer_address"],
                    items=items,
                    conversation_id=conversation.id,
                    db=db
                )
                if "error" not in order_result:
                    # 3. Update customer memory after order
                    try:
                        from services.customer_memory import get_or_create_memory, update_memory_after_order
                        memory, _ = await get_or_create_memory(
                            seller_id=seller.id,
                            session_id=session_id,
                            db=db,
                            phone=parsed["customer_phone"],
                            name=parsed["customer_name"],
                        )
                        await update_memory_after_order(memory, items, order_result["total"], db)
                    except Exception as e:
                        logger.warning(f"Failed to update memory after order: {e}")
        except Exception as e:
            logger.error(f"Order creation failed: {e}", exc_info=True)

    # Save AI response
    ai_msg = Message(
        conversation_id=conversation.id,
        role=MessageRole.AI,
        content=ai_response_text,
    )
    db.add(ai_msg)

    # Track analytics
    analytics = ChatAnalytics(
        conversation_id=conversation.id,
        seller_id=seller.id,
        intent=intent,
        sales_stage=sales_stage,
        response_time_ms=response_time_ms,
        user_message_length=len(req.message),
        ai_response_length=len(ai_response_text),
        converted_to_order="ORDER CONFIRMED" in ai_response_text.upper(),
    )
    db.add(analytics)
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
    """List all conversations for the current seller (optimized: 1 query instead of N+1)."""
    from sqlalchemy import desc
    from sqlalchemy.orm import selectinload
    
    # Single query: fetch conversations with eager-loaded messages (BUG 12 FIX)
    result = await db.execute(
        select(Conversation)
        .where(Conversation.seller_id == current_user.id)
        .options(selectinload(Conversation.messages))
        .order_by(desc(Conversation.updated_at))
        .limit(50)
    )
    conversations = result.scalars().unique().all()
    
    response = []
    for conv in conversations:
        msgs = conv.messages or []
        last_msg = msgs[-1] if msgs else None
        
        response.append({
            "id": conv.id,
            "session_id": conv.session_id,
            "customer_name": conv.customer_name,
            "is_urgent": conv.is_urgent,
            "message_count": len(msgs),
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

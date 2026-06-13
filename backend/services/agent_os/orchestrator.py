"""JUALIN OS — Orchestrator (Manajer AI). Merutekan giliran chat ke agen yang tepat."""
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from core.logging_config import get_logger
from models.agent_os import AgentRun
from services.agent_os.negotiation import is_negotiation, run_negotiation_turn

settings = get_settings()
logger = get_logger(__name__)


async def agent_os_handle_turn(*, seller, conversation, message, history, db: AsyncSession,
                               memory_context: str = "") -> dict:
    """
    Putuskan agen mana yang menangani giliran ini.
    Untuk MVP: hanya Negotiator yang 'mengambil alih'. Selain itu -> handled=False (Sales lama jalan).
    Menambah ke sesi (flush) — route pemanggil yang commit.
    """
    if not settings.ENABLE_AGENT_OS:
        return {"handled": False}
    try:
        if is_negotiation(message):
            # Savepoint: bila negosiasi gagal (mis. tabel belum dimigrasi di VPS),
            # rollback HANYA savepoint ini — transaksi chat utama tetap sehat.
            async with db.begin_nested():
                result = await run_negotiation_turn(
                    seller=seller, conversation=conversation, message=message, history=history, db=db,
                )
            if result.get("handled"):
                return result
        return {"handled": False}
    except Exception as e:
        logger.warning(f"agent_os_handle_turn error: {e}")
        return {"handled": False}


async def record_sales_activity(seller_id: int, conversation_id: int, intent: str,
                                sales_stage: str, order_created: bool, db: AsyncSession):
    """Catat aktivitas Pramuniaga untuk activity feed (giliran non-negosiasi)."""
    summary = f"Pramuniaga menangani percakapan (intent: {intent}, stage: {sales_stage})"
    if order_created:
        summary = "Pramuniaga menutup order dari percakapan 🎉"
    # Savepoint agar kegagalan pencatatan tidak meracuni transaksi chat utama.
    async with db.begin_nested():
        db.add(AgentRun(
            seller_id=seller_id, agent_role="sales", trigger="chat", status="done",
            summary=summary, detail_json={"intent": intent, "stage": sales_stage, "order_created": order_created},
            conversation_id=conversation_id,
        ))
        await db.flush()

"""JUALIN OS — Laporan Harian (Daily Manager Brief) dari Orchestrator."""
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from core.logging_config import get_logger
from models.agent_os import AgentRun, AgentApproval
from services.agent_os.finance import build_finance_snapshot
from services.agent_os.inventory import scan_low_stock

settings = get_settings()
logger = get_logger(__name__)


async def build_daily_brief(seller_id: int, db: AsyncSession) -> dict:
    """Susun ringkasan 24 jam terakhir + narasi LLM. Hanya membaca + 1 AgentRun opsional."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    # Hitung aktivitas per peran
    r = await db.execute(
        select(AgentRun.agent_role, func.count(AgentRun.id))
        .where(AgentRun.seller_id == seller_id)
        .where(AgentRun.created_at >= since)
        .group_by(AgentRun.agent_role)
    )
    by_role = {role: int(cnt) for role, cnt in r.all()}

    # Approval menunggu
    r2 = await db.execute(
        select(func.count(AgentApproval.id))
        .where(AgentApproval.seller_id == seller_id)
        .where(AgentApproval.status == "pending")
    )
    pending_approvals = int(r2.scalar() or 0)

    finance = await build_finance_snapshot(seller_id, db)
    low_stock = await scan_low_stock(seller_id, db, threshold=3)

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "activity_by_role": by_role,
        "pending_approvals": pending_approvals,
        "finance": finance,
        "low_stock_count": len(low_stock),
        "low_stock_items": low_stock[:5],
    }

    # Narasi LLM (dengan fallback)
    narrative = _fallback_narrative(data)
    try:
        from ai.agent import llm_client
        prompt = [
            {"role": "system", "content": (
                "Kamu manajer toko AI. Tulis ringkasan harian SINGKAT (3-4 kalimat) untuk pemilik toko UMKM "
                "dalam Bahasa Indonesia santai, berdasarkan data JSON. Sebutkan angka penting. Akhiri dengan "
                "1 saran tindakan. Jangan mengarang angka di luar data."
            )},
            {"role": "user", "content": str(data)},
        ]
        resp = await llm_client.chat.completions.create(
            model=settings.LLM_MODEL, messages=prompt, temperature=0.5, max_tokens=220,
        )
        text = (resp.choices[0].message.content or "").strip()
        if text:
            narrative = text
    except Exception as e:
        logger.warning(f"brief narrative LLM failed: {e}")

    data["narrative"] = narrative

    # Simpan jejak brief sebagai AgentRun orchestrator (flush; pemanggil commit)
    db.add(AgentRun(
        seller_id=seller_id, agent_role="orchestrator", trigger="brief", status="done",
        summary="Laporan harian dibuat", detail_json={"narrative": narrative, "finance": finance},
    ))
    await db.flush()
    return data


def _fallback_narrative(data: dict) -> str:
    f = data["finance"]
    return (
        f"Hari ini tim AI memproses {sum(data['activity_by_role'].values())} aktivitas. "
        f"Omzet Rp {f['revenue_today']:,.0f} ({f['paid_today']} order lunas), "
        f"{f['pending_today']} pembayaran tertunda senilai Rp {f['pending_value']:,.0f}. "
        f"{data['pending_approvals']} keputusan menunggu persetujuan; "
        f"{data['low_stock_count']} produk stok menipis. "
        f"Saran: tindak lanjuti pembayaran tertunda dan restock produk yang menipis."
    )

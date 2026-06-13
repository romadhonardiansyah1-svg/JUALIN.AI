# PLAN IMPLEMENTASI — JUALIN OS Core (MVP)

> **Untuk agen pelaksana.** Dokumen ini adalah blueprint langkah-demi-langkah membangun **JUALIN OS Core**: lapisan multi-agen otonom (Orchestrator + Negotiator + Inventory + Growth + Finance) di atas basis kode JUALIN.AI yang sudah ada.
>
> **Baca seluruh bagian "ATURAN EMAS" dulu, lalu kerjakan FASE 0 → FASE 11 berurutan.** Jangan melompat. Setiap fase punya langkah verifikasi — **jangan lanjut ke fase berikut sebelum verifikasi fase saat ini lulus.**

---

## ATURAN EMAS (WAJIB dipatuhi sebelum menulis kode apa pun)

1. **Jangan ubah perilaku lama.** Semua fitur baru di-gate oleh flag `ENABLE_AGENT_OS`. Jika flag mati, aplikasi harus berperilaku 100% seperti sebelumnya.
2. **Satu sesi DB, sekuensial.** `AsyncSession` TIDAK aman untuk dipakai konkuren. Jangan pernah `asyncio.gather` beberapa query pada `db` yang sama. Selalu `await` satu per satu.
3. **Tambah ke sesi, jangan commit di tengah.** Fungsi agent_os menambah baris via `db.add(...)` lalu `await db.flush()` (BUKAN `commit`). Commit dilakukan oleh pemanggil (route chat) di akhir. Untuk worker/cron, commit dilakukan di fungsi cycle.
4. **Model baru WAJIB di-import** di `backend/models/__init__.py`, kalau tidak tabelnya tidak akan dibuat.
5. **Gaya kode ikuti yang ada.** Model pakai gaya `Column(...)` klasik (lihat `models/scale_core.py`). Route pakai `Depends(get_current_user)` + `Depends(get_db)`. Audit pakai `record_audit(...)`.
6. **Angka harga dikontrol ENGINE, bukan LLM.** Di mesin negosiasi, harga SELALU dihitung fungsi deterministik. LLM hanya merangkai kalimat. Jika kalimat LLM tidak memuat angka yang benar → pakai kalimat fallback.
7. **Lingkungan = Windows + PowerShell.** Untuk menjalankan perintah backend, aktifkan venv: `backend\venv\Scripts\activate`. Pisahkan perintah dengan `;` (bukan `&&`) di PowerShell.
8. **Frontend = Next.js 16 (ada breaking changes).** Untuk halaman dashboard baru, **TIRU PERSIS pola file halaman dashboard yang sudah ada** (mis. `frontend/app/dashboard/offers/page.js`): `"use client"`, `import { api } from "@/lib/api"`, `useEffect`/`useState`. Jangan pakai API Next.js yang tidak kamu lihat dipakai di file existing.
9. **Jangan jalankan test berat / migrasi destruktif.** Untuk dev/demo cukup `AUTO_CREATE_TABLES=True` (sudah default) yang otomatis `create_all`. Migrasi Alembic disediakan untuk produksi (Fase 2D) tapi tidak wajib dijalankan untuk demo.
10. **Setelah tiap fase, jalankan verifikasi.** Jika gagal, perbaiki dulu sebelum lanjut.

---

## 0. RINGKASAN ARSITEKTUR MVP

```
routes_chat.send_message (chat publik)
        │  ENABLE_AGENT_OS?
        ▼
services/agent_os/orchestrator.py  ── agent_os_handle_turn()
        │   ├─ is_negotiation(message)?  ──▶  negotiation.run_negotiation_turn()
        │   │                                   ├─ get_or_create_policy()
        │   │                                   ├─ _resolve_focus_product() (pgvector)
        │   │                                   ├─ decide_offer()  ← ENGINE deterministik (margin-safe)
        │   │                                   ├─ NegotiationState (simpan ronde)
        │   │                                   ├─ AgentApproval (jika diskon > ambang) ← HITL
        │   │                                   ├─ _phrase_offer() ← LLM merangkai kalimat
        │   │                                   └─ AgentRun (catat aktivitas)
        │   └─ else: handled=False  →  alur Sales lama berjalan + record_sales_activity()
        ▼
WORKER cron (arq)  ── cron_agent_os_tick → cycles.run_all_seller_cycles()
        ├─ inventory.scan_low_stock()   → AgentRun
        └─ growth.run_growth_cycle()    → AgentRun

API routes_agent_os.py  (/api/agent-os/*)  → dipakai halaman dashboard "AI Crew"
  overview · activity · brief · policy · approvals · negotiations

Frontend /dashboard/agent-os  → Pusat Komando AI Crew
```

### Daftar file — BUAT BARU (8 file)
| File | Isi |
|---|---|
| `backend/models/agent_os.py` | 4 model: AgentPolicy, AgentRun, AgentApproval, NegotiationState |
| `backend/services/agent_os/__init__.py` | penanda package (kosong) |
| `backend/services/agent_os/policy.py` | `get_or_create_policy()` |
| `backend/services/agent_os/negotiation.py` | mesin nego (engine + LLM phrasing) |
| `backend/services/agent_os/inventory.py` | guard stok + scan low-stock |
| `backend/services/agent_os/finance.py` | snapshot keuangan harian |
| `backend/services/agent_os/growth.py` | siklus proaktif (tagih/win-back) |
| `backend/services/agent_os/brief.py` | Laporan Harian (aggregasi + narasi LLM) |
| `backend/services/agent_os/cycles.py` | loop semua seller untuk worker |
| `backend/services/agent_os/orchestrator.py` | router turn chat + record aktivitas |
| `backend/api/routes_agent_os.py` | endpoint /api/agent-os/* |
| `backend/seed/seed_agent_os.py` | seed cost_price + policy demo |
| `backend/alembic/versions/20260613_0006_agent_os.py` | migrasi produksi |
| `frontend/app/dashboard/agent-os/page.js` | halaman Pusat Komando AI Crew |

*(Catatan: tabel di atas 14 entri — semuanya file baru.)*

### Daftar file — EDIT (7 file)
| File | Perubahan |
|---|---|
| `backend/config.py` | +flag `ENABLE_AGENT_OS` & default nego |
| `backend/models/product.py` | +kolom `cost_price` |
| `backend/models/__init__.py` | +import model agent_os |
| `backend/models/database.py` | +ALTER TABLE patch `products.cost_price` |
| `backend/api/routes_chat.py` | +hook orchestrator (3 sisipan kecil) |
| `backend/main.py` | +import & mount router agent_os |
| `backend/worker.py` | +cron `cron_agent_os_tick` |
| `frontend/lib/api.js` | +helper agent-os |
| `frontend/app/dashboard/layout.js` | +item nav "AI Crew" |

---

## FASE 0 — Prasyarat & verifikasi lingkungan

**Langkah 0.1** Pastikan DB & Redis jalan, dan backend bisa start.
```powershell
# dari root repo
docker compose up -d db redis
cd backend
.\venv\Scripts\activate
python -m seed.seed_data   # idempotent; aman dijalankan ulang
uvicorn main:app --reload
```
**Verifikasi 0:** Buka `http://localhost:8000/health` → JSON `{"status":"ok", "database":"connected", ...}`. Jika `database` bukan `connected`, perbaiki dulu (cek `DATABASE_URL`). **Stop uvicorn (Ctrl+C)** sebelum mulai edit.

---

## FASE 1 — Config flags

**File:** `backend/config.py`
**Langkah 1.1** Cari blok `# Market Acceptance feature flags` (sekitar baris 29-34). **Tepat di bawah baris** `IMPERSONATION_TOKEN_MINUTES: int = 15`, tambahkan:

```python
    # ── JUALIN OS (Multi-Agent Business OS) ──
    ENABLE_AGENT_OS: bool = True
    AGENT_OS_DEFAULT_MAX_DISCOUNT: float = 15.0      # diskon maksimum (%) default per seller
    AGENT_OS_DEFAULT_MARGIN_FLOOR: float = 10.0      # margin minimum di atas modal (%) default
    AGENT_OS_APPROVAL_ABOVE_PERCENT: float = 10.0    # diskon di atas ini butuh persetujuan
    AGENT_OS_LOW_STOCK_THRESHOLD: int = 3            # stok <= ini dianggap menipis
```

**Verifikasi 1:**
```powershell
cd backend ; .\venv\Scripts\activate ; python -c "from config import get_settings; print(get_settings().ENABLE_AGENT_OS)"
```
Harus mencetak `True`.

---

## FASE 2 — Data model

### 2A. Kolom `cost_price` pada Product
**File:** `backend/models/product.py`
**Langkah 2A.1** Cari baris:
```python
    kategori = Column(String(100), default="umum")
    foto_url = Column(String(500), default="")
```
**Tepat di bawahnya** tambahkan:
```python
    cost_price = Column(Float, default=0)  # modal/HPP untuk negosiasi aman-margin (JUALIN OS)
```
*(`Float` sudah ada di import baris `from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text` — tidak perlu ubah import.)*

### 2B. Model baru — buat file `backend/models/agent_os.py`
**Isi LENGKAP:**
```python
"""
JUALIN OS — Multi-Agent Business OS core models.

Tabel:
- agent_policies     : konfigurasi otonomi & guardrail per seller (1 baris / seller)
- agent_runs         : log aktivitas — 1 baris per aktivasi agen (the "activity feed")
- agent_approvals    : antrean human-in-the-loop untuk aksi berisiko
- negotiation_states : state tawar-menawar per percakapan
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, JSON, Float, Boolean, UniqueConstraint,
)
from sqlalchemy.sql import func

from models.database import Base

# Peran agen yang dikenal di seluruh OS
AGENT_ROLES = ("orchestrator", "sales", "negotiator", "inventory", "growth", "finance", "cs")


class AgentPolicy(Base):
    __tablename__ = "agent_policies"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Tingkat otonomi: assist | auto_with_approval | full_auto
    autonomy_level = Column(String(30), default="auto_with_approval", nullable=False)

    # Sakelar per-agen
    allow_auto_negotiation = Column(Boolean, default=True, nullable=False)
    allow_auto_followup = Column(Boolean, default=True, nullable=False)
    allow_low_stock_alert = Column(Boolean, default=True, nullable=False)
    daily_brief_enabled = Column(Boolean, default=True, nullable=False)

    # Guardrail negosiasi (persen)
    max_discount_percent = Column(Float, default=15.0, nullable=False)
    margin_floor_percent = Column(Float, default=10.0, nullable=False)
    require_approval_above_percent = Column(Float, default=10.0, nullable=False)
    nego_max_rounds = Column(Integer, default=3, nullable=False)

    # Inventory
    low_stock_threshold = Column(Integer, default=3, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("seller_id", name="uq_agent_policy_seller"),
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    agent_role = Column(String(30), nullable=False, index=True)
    trigger = Column(String(30), default="chat", nullable=False)   # chat|cron|payment|manual
    status = Column(String(20), default="done", nullable=False)    # done|escalated|blocked|failed|needs_approval
    summary = Column(String(500), default="")
    detail_json = Column(JSON, default=dict)

    conversation_id = Column(Integer, nullable=True, index=True)
    customer_id = Column(Integer, nullable=True, index=True)
    order_id = Column(Integer, nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class AgentApproval(Base):
    __tablename__ = "agent_approvals"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    agent_role = Column(String(30), default="negotiator", nullable=False)
    action_type = Column(String(50), nullable=False, index=True)   # apply_discount|refund|broadcast|large_order
    title = Column(String(255), default="")
    detail_json = Column(JSON, default=dict)
    status = Column(String(20), default="pending", nullable=False, index=True)  # pending|approved|rejected|expired
    reason = Column(String(500), default="")
    decided_by = Column(Integer, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)

    conversation_id = Column(Integer, nullable=True, index=True)
    order_id = Column(Integer, nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class NegotiationState(Base):
    __tablename__ = "negotiation_states"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(Integer, nullable=False, index=True)
    product_id = Column(Integer, nullable=True, index=True)

    list_price = Column(Float, default=0)
    floor_price = Column(Float, default=0)
    current_offer = Column(Float, default=0)
    last_customer_ask = Column(Float, default=0)
    rounds = Column(Integer, default=0)
    status = Column(String(20), default="active", nullable=False)  # active|accepted|rejected|escalated
    history_json = Column(JSON, default=list)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
```

### 2C. Daftarkan model — edit `backend/models/__init__.py`
**Langkah 2C.1** Cari blok "Market Acceptance models" (sekitar baris 42-47), setelah baris:
```python
from models.concierge_checklist import ConciergeChecklist
```
**tambahkan:**
```python

# JUALIN OS models
from models.agent_os import AgentPolicy, AgentRun, AgentApproval, NegotiationState
```
**Langkah 2C.2** Di dalam list `__all__`, sebelum baris penutup `]`, tambahkan:
```python
    "AgentPolicy", "AgentRun", "AgentApproval", "NegotiationState",
```

### 2D. Forward-only patch — edit `backend/models/database.py`
**Langkah 2D.1** Di fungsi `init_db()`, cari blok komentar `# ── Market Acceptance Schema Patches ──`. **Sebelum** baris terakhir fungsi (setelah patch Sprint 5 `daily_seller_metrics`), tambahkan:
```python

            # ── JUALIN OS Schema Patches ──
            await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS cost_price FLOAT DEFAULT 0"))
```
*(Tabel `agent_policies`, `agent_runs`, `agent_approvals`, `negotiation_states` dibuat otomatis oleh `create_all` setelah model di-import di 2C.)*

### 2E. Migrasi Alembic (untuk PRODUKSI — opsional untuk demo)
Buat file `backend/alembic/versions/20260613_0006_agent_os.py`:
```python
"""JUALIN OS: agent_policies, agent_runs, agent_approvals, negotiation_states + products.cost_price

Revision ID: 20260613_0006
Revises: 20260605_0005
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa

revision = "20260613_0006"
down_revision = "20260605_0005"
branch_labels = None
depends_on = None


def _table_exists(conn, name):
    return conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"),
        {"t": name},
    ).scalar()


def _column_exists(conn, table, column):
    return conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c)"
        ),
        {"t": table, "c": column},
    ).scalar()


def upgrade():
    conn = op.get_bind()

    if not _column_exists(conn, "products", "cost_price"):
        op.add_column("products", sa.Column("cost_price", sa.Float, server_default="0"))

    if not _table_exists(conn, "agent_policies"):
        op.create_table(
            "agent_policies",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("autonomy_level", sa.String(30), nullable=False, server_default="auto_with_approval"),
            sa.Column("allow_auto_negotiation", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("allow_auto_followup", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("allow_low_stock_alert", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("daily_brief_enabled", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("max_discount_percent", sa.Float, nullable=False, server_default="15"),
            sa.Column("margin_floor_percent", sa.Float, nullable=False, server_default="10"),
            sa.Column("require_approval_above_percent", sa.Float, nullable=False, server_default="10"),
            sa.Column("nego_max_rounds", sa.Integer, nullable=False, server_default="3"),
            sa.Column("low_stock_threshold", sa.Integer, nullable=False, server_default="3"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("seller_id", name="uq_agent_policy_seller"),
        )

    if not _table_exists(conn, "agent_runs"):
        op.create_table(
            "agent_runs",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("agent_role", sa.String(30), nullable=False, index=True),
            sa.Column("trigger", sa.String(30), nullable=False, server_default="chat"),
            sa.Column("status", sa.String(20), nullable=False, server_default="done"),
            sa.Column("summary", sa.String(500), server_default=""),
            sa.Column("detail_json", sa.JSON, server_default="{}"),
            sa.Column("conversation_id", sa.Integer, index=True),
            sa.Column("customer_id", sa.Integer, index=True),
            sa.Column("order_id", sa.Integer, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        )

    if not _table_exists(conn, "agent_approvals"):
        op.create_table(
            "agent_approvals",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("agent_role", sa.String(30), nullable=False, server_default="negotiator"),
            sa.Column("action_type", sa.String(50), nullable=False, index=True),
            sa.Column("title", sa.String(255), server_default=""),
            sa.Column("detail_json", sa.JSON, server_default="{}"),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending", index=True),
            sa.Column("reason", sa.String(500), server_default=""),
            sa.Column("decided_by", sa.Integer),
            sa.Column("decided_at", sa.DateTime(timezone=True)),
            sa.Column("conversation_id", sa.Integer, index=True),
            sa.Column("order_id", sa.Integer, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        )

    if not _table_exists(conn, "negotiation_states"):
        op.create_table(
            "negotiation_states",
            sa.Column("id", sa.Integer, primary_key=True, index=True),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("conversation_id", sa.Integer, nullable=False, index=True),
            sa.Column("product_id", sa.Integer, index=True),
            sa.Column("list_price", sa.Float, server_default="0"),
            sa.Column("floor_price", sa.Float, server_default="0"),
            sa.Column("current_offer", sa.Float, server_default="0"),
            sa.Column("last_customer_ask", sa.Float, server_default="0"),
            sa.Column("rounds", sa.Integer, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("history_json", sa.JSON, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )


def downgrade():
    for t in ("negotiation_states", "agent_approvals", "agent_runs", "agent_policies"):
        op.execute(f"DROP TABLE IF EXISTS {t}")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS cost_price")
```

**Verifikasi 2:** Start backend sekali (`uvicorn main:app --reload`). Di log startup harus muncul `✅ Database initialized`. Lalu cek tabel ada:
```powershell
docker compose exec db psql -U postgres -d jualin_ai -c "\dt agent_*"
```
Harus muncul `agent_policies`, `agent_runs`, `agent_approvals` (dan `negotiation_states` via `\dt negotiation_states`). **Stop uvicorn.**

---

## FASE 3 — Mesin Negosiasi (jantung kebaruan)

### 3A. Package marker — buat `backend/services/agent_os/__init__.py`
Isi: **kosong** (file kosong, tanpa konten). Cukup buat filenya.

### 3B. Helper policy — buat `backend/services/agent_os/policy.py`
```python
"""Helper kebijakan agen per-seller."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.agent_os import AgentPolicy

settings = get_settings()


async def get_or_create_policy(seller_id: int, db: AsyncSession) -> AgentPolicy:
    """Ambil AgentPolicy seller; buat default jika belum ada. Memakai flush (bukan commit)."""
    result = await db.execute(select(AgentPolicy).where(AgentPolicy.seller_id == seller_id))
    policy = result.scalar_one_or_none()
    if policy:
        return policy

    policy = AgentPolicy(
        seller_id=seller_id,
        max_discount_percent=settings.AGENT_OS_DEFAULT_MAX_DISCOUNT,
        margin_floor_percent=settings.AGENT_OS_DEFAULT_MARGIN_FLOOR,
        require_approval_above_percent=settings.AGENT_OS_APPROVAL_ABOVE_PERCENT,
        low_stock_threshold=settings.AGENT_OS_LOW_STOCK_THRESHOLD,
    )
    db.add(policy)
    await db.flush()
    return policy
```

### 3C. Mesin negosiasi — buat `backend/services/agent_os/negotiation.py`
```python
"""
JUALIN OS — Mesin Negosiasi (Juru Tawar AI).

PRINSIP UTAMA: ANGKA dikontrol fungsi deterministik (decide_offer), KATA dirangkai LLM.
Harga penawaran DIJAMIN berada di rentang [floor_price, list_price] — tidak pernah jual rugi.
"""
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from core.logging_config import get_logger
from models.product import Product
from models.agent_os import AgentRun, AgentApproval, NegotiationState
from services.agent_os.policy import get_or_create_policy

settings = get_settings()
logger = get_logger(__name__)


# ── Deteksi intent negosiasi ──
_NEGO_PATTERNS = [
    r'\bboleh\s*kurang\b', r'\bbisa\s*kurang\b', r'\bnego\b', r'\bngenego\b',
    r'\bkurangin\b', r'\bmurahin\b', r'\bpotongan\b', r'\bdiskon\b', r'\btawar\b',
    r'\bboleh\s*\d', r'\bkalau\s*\d', r'\b\d+\s*(rb|ribu|k)\b', r'\b\d+\s*aja\b',
    r'\bgocengan\b', r'\bsadis\b',
]


def is_negotiation(text: str) -> bool:
    """True jika pesan mengandung sinyal tawar-menawar."""
    t = (text or "").lower()
    return any(re.search(p, t) for p in _NEGO_PATTERNS)


def parse_price_ask(text: str) -> float | None:
    """
    Ekstrak harga yang diminta customer (dalam rupiah). None jika tidak ada.
    Contoh: '150 ribu'/'150rb'/'150k' -> 150000 ; 'rp 150000' -> 150000 ;
            'boleh 75?' -> 75000 (angka 2-3 digit dianggap ribuan).
    """
    t = (text or "").lower().replace(".", "").replace(",", "")
    m = re.search(r'(\d+)\s*(rb|ribu|k)\b', t)
    if m:
        return float(m.group(1)) * 1000
    m = re.search(r'rp\s*(\d{3,9})', t)
    if m:
        return float(m.group(1))
    m = re.search(r'\b(\d{4,9})\b', t)        # angka 4-9 digit = harga utuh
    if m:
        return float(m.group(1))
    m = re.search(r'\b(\d{2,3})\b', t)         # angka 2-3 digit di konteks nego = ribuan
    if m:
        return float(m.group(1)) * 1000
    return None


def compute_floor_price(list_price: float, cost_price: float, policy) -> float:
    """
    Lantai harga = batas terendah yang boleh ditawarkan.
    = max( harga * (1 - diskon_maks%), modal * (1 + margin_floor%) ).
    Jika modal tidak diketahui (0), pakai batas diskon saja.
    """
    by_discount = list_price * (1 - policy.max_discount_percent / 100.0)
    if cost_price and cost_price > 0:
        by_margin = cost_price * (1 + policy.margin_floor_percent / 100.0)
        return max(by_discount, by_margin)
    return by_discount


def decide_offer(list_price: float, floor_price: float, customer_ask: float | None,
                 round_index: int, policy) -> dict:
    """
    Fungsi DETERMINISTIK. Mengembalikan penawaran yang DIJAMIN di [floor_price, list_price].

    Concession ladder: ronde 0 -> beri 40% jalan dari list ke floor, ronde 1 -> 70%, ronde 2+ -> 100% (floor).
    """
    rounds_max = max(1, policy.nego_max_rounds)
    schedule = [0.40, 0.70, 1.00]
    frac = schedule[min(round_index, len(schedule) - 1)]
    concession_price = list_price - (list_price - floor_price) * frac  # >= floor

    if customer_ask is None:
        offer, decision = concession_price, "counter"
    elif customer_ask >= list_price:
        offer, decision = list_price, "accept"
    elif customer_ask >= concession_price:
        # Permintaan customer di atas garis konsesi -> kabulkan (tetap >= floor)
        offer, decision = customer_ask, "accept"
    elif customer_ask >= floor_price:
        # Di bawah konsesi ronde ini tapi masih di atas floor -> tawar di garis konsesi
        offer, decision = concession_price, "counter"
    else:
        # Di bawah floor -> tawar harga terbaik ronde ini (tidak pernah di bawah floor)
        offer, decision = concession_price, "counter_floor"

    offer = round(max(floor_price, min(offer, list_price)))
    discount_pct = 0.0 if list_price <= 0 else round((list_price - offer) / list_price * 100, 1)
    is_final = round_index >= rounds_max - 1 or offer <= floor_price + 0.5
    requires_approval = discount_pct > policy.require_approval_above_percent
    return {
        "decision": decision,
        "offer_price": offer,
        "discount_pct": discount_pct,
        "floor_price": round(floor_price),
        "list_price": round(list_price),
        "is_final": is_final,
        "requires_approval": requires_approval,
        "round": round_index,
    }


async def _resolve_focus_product(seller_id, conversation, history, message, db):
    """Tebak produk yang sedang ditawar dari konteks percakapan (pgvector)."""
    from ai.agent import search_products_semantic
    texts = []
    for m in (history or [])[-4:]:
        c = getattr(m, "content", None)
        if c is None and isinstance(m, dict):
            c = m.get("content", "")
        if c:
            texts.append(c)
    texts.append(message or "")
    query = " ".join(texts).strip()
    if not query:
        return None
    results = await search_products_semantic(query, seller_id, db, limit=1)
    if not results:
        return None
    r = await db.execute(select(Product).where(Product.id == results[0]["id"]))
    return r.scalar_one_or_none()


async def _get_or_create_state(seller_id, conversation_id, product, policy, db) -> NegotiationState:
    r = await db.execute(
        select(NegotiationState)
        .where(NegotiationState.conversation_id == conversation_id)
        .where(NegotiationState.product_id == product.id)
        .where(NegotiationState.status == "active")
    )
    state = r.scalar_one_or_none()
    if state:
        return state
    list_price = float(product.harga or 0)
    cost = float(getattr(product, "cost_price", 0) or 0)
    floor = compute_floor_price(list_price, cost, policy)
    state = NegotiationState(
        seller_id=seller_id, conversation_id=conversation_id, product_id=product.id,
        list_price=list_price, floor_price=floor, current_offer=list_price, history_json=[],
    )
    db.add(state)
    await db.flush()
    return state


async def _phrase_offer(seller, product, decision, requires_approval: bool) -> str:
    """LLM merangkai kalimat di sekitar angka engine. Fallback jika LLM gagal/menyimpang."""
    from ai.agent import llm_client
    offer = decision["offer_price"]
    list_price = decision["list_price"]

    if requires_approval:
        fallback = f"Boleh kak 🙏 sebentar ya aku cek dulu ke owner buat harga spesial {product.nama}."
    elif decision["decision"] == "accept":
        fallback = f"Siap kak! {product.nama} aku kasih Rp {offer:,.0f} ya 😊 Lanjut order?"
    elif decision["decision"] == "counter_floor":
        fallback = (f"Maaf kak belum bisa segitu 🙏 tapi {product.nama} aku kasih harga terbaik "
                    f"Rp {offer:,.0f} (normal Rp {list_price:,.0f}). Gimana kak?")
    else:
        fallback = (f"Boleh nego kak 😊 {product.nama} aku kasih Rp {offer:,.0f} "
                    f"(normal Rp {list_price:,.0f}). Mau aku buatin ordernya?")

    prompt = [
        {"role": "system", "content": (
            "Kamu CS toko online Indonesia yang ramah. Tulis SATU balasan singkat (maks 2 kalimat) "
            "untuk situasi tawar-menawar. WAJIB memakai PERSIS angka rupiah yang diberikan, "
            "JANGAN mengarang angka lain. Bahasa santai, maksimal 1 emoji."
        )},
        {"role": "user", "content": (
            f"Produk: {product.nama}. Harga normal Rp {int(list_price)}. "
            f"Keputusan: {decision['decision']}. Harga yang ditawarkan ke pembeli: Rp {int(offer)}. "
            f"requires_approval={requires_approval}. Tulis balasannya."
        )},
    ]
    try:
        resp = await llm_client.chat.completions.create(
            model=settings.LLM_MODEL, messages=prompt, temperature=0.5, max_tokens=120,
        )
        text = (resp.choices[0].message.content or "").strip()
        # Guard angka: kalimat harus memuat harga engine, kalau tidak -> fallback
        flat = text.replace(".", "").replace(",", "")
        if requires_approval or str(int(offer)) in flat:
            return text or fallback
        return fallback
    except Exception as e:
        logger.warning(f"_phrase_offer LLM failed: {e}")
        return fallback


async def run_negotiation_turn(*, seller, conversation, message, history, db) -> dict:
    """
    Tangani satu giliran negosiasi. Menambah ke sesi (flush) — pemanggil yang commit.
    Return: {handled, reply, intent, stage, order_created, agent_run_id, approval_id}
    """
    policy = await get_or_create_policy(seller.id, db)
    if not policy.allow_auto_negotiation:
        return {"handled": False}

    product = await _resolve_focus_product(seller.id, conversation, history, message, db)
    if not product:
        return {"handled": False}  # tanpa produk fokus, biar Sales lama yang jawab

    state = await _get_or_create_state(seller.id, conversation.id, product, policy, db)
    customer_ask = parse_price_ask(message)
    decision = decide_offer(state.list_price, state.floor_price, customer_ask, state.rounds, policy)

    # Update state
    state.rounds += 1
    state.current_offer = decision["offer_price"]
    if customer_ask:
        state.last_customer_ask = customer_ask
    hist = list(state.history_json or [])
    hist.append({
        "round": state.rounds, "ask": customer_ask,
        "offer": decision["offer_price"], "decision": decision["decision"],
    })
    state.history_json = hist[-10:]
    if decision["decision"] == "accept":
        state.status = "accepted"

    # HITL approval bila perlu
    approval_id = None
    if decision["requires_approval"]:
        approval = AgentApproval(
            seller_id=seller.id, agent_role="negotiator", action_type="apply_discount",
            title=f"Diskon {decision['discount_pct']}% untuk {product.nama} (Rp {decision['offer_price']:,.0f})",
            detail_json={"product_id": product.id, **decision, "customer_ask": customer_ask},
            conversation_id=conversation.id, status="pending",
        )
        db.add(approval)
        await db.flush()
        approval_id = approval.id
        state.status = "escalated"

    reply = await _phrase_offer(seller, product, decision, decision["requires_approval"])

    run = AgentRun(
        seller_id=seller.id, agent_role="negotiator", trigger="chat",
        status="needs_approval" if decision["requires_approval"] else "done",
        summary=(f"Nego {product.nama}: minta Rp {int(customer_ask):,} → tawar Rp {decision['offer_price']:,} "
                 f"({decision['discount_pct']}%)" if customer_ask
                 else f"Nego {product.nama}: tawar Rp {decision['offer_price']:,}"),
        detail_json={"product": product.nama, **decision, "customer_ask": customer_ask},
        conversation_id=conversation.id,
    )
    db.add(run)
    await db.flush()

    return {
        "handled": True, "reply": reply, "intent": "order", "stage": "negotiation",
        "order_created": False, "agent_run_id": run.id, "approval_id": approval_id,
    }
```

**Verifikasi 3 (uji engine murni, tanpa DB):**
```powershell
cd backend ; .\venv\Scripts\activate
python -c "from types import SimpleNamespace as N; from services.agent_os.negotiation import decide_offer, parse_price_ask, compute_floor_price; pol=N(max_discount_percent=15,margin_floor_percent=10,require_approval_above_percent=10,nego_max_rounds=3); floor=compute_floor_price(189000, 110000, pol); print('floor', floor); print(parse_price_ask('boleh 150 ribu?')); print(decide_offer(189000, floor, 150000, 0, pol)); print(decide_offer(189000, floor, 100000, 0, pol))"
```
**Harapan:** `floor 160600.0` (modal 110k×1.1=121k vs 189k×0.85=160.65k → ambil yang lebih besar = 160650; dibulatkan saat decide). `parse_price_ask` → `150000.0`. `decide_offer(...,150000,...)` → `offer_price` di antara floor dan 189000, **tidak pernah < floor**. `decide_offer(...,100000,...)` (di bawah floor) → `decision: 'counter_floor'`, `offer_price` >= floor. **Pastikan tidak ada offer di bawah floor.**

---

## FASE 4 — Agen Inventory, Finance, Growth, Brief

### 4A. Inventory — buat `backend/services/agent_os/inventory.py`
```python
"""JUALIN OS — Gudang AI (Inventory)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging_config import get_logger
from models.product import Product
from models.agent_os import AgentRun

logger = get_logger(__name__)


async def check_stock_guard(seller_id: int, items: list[dict], db: AsyncSession) -> dict:
    """Verifikasi stok cukup untuk daftar item [{product_id, qty}]. Return {ok, issues}."""
    issues = []
    for it in items or []:
        pid = it.get("product_id")
        qty = int(it.get("qty", 1))
        if not pid:
            continue
        r = await db.execute(select(Product).where(Product.id == pid, Product.seller_id == seller_id))
        p = r.scalar_one_or_none()
        if not p or p.is_active != 1:
            issues.append({"product_id": pid, "reason": "tidak ditemukan"})
        elif p.stok < qty:
            issues.append({"product_id": pid, "nama": p.nama, "reason": f"stok {p.stok} < {qty}"})
    return {"ok": len(issues) == 0, "issues": issues}


async def scan_low_stock(seller_id: int, db: AsyncSession, threshold: int = 3) -> list[dict]:
    """Pindai produk stok menipis. Catat AgentRun bila ada temuan (flush, bukan commit)."""
    r = await db.execute(
        select(Product)
        .where(Product.seller_id == seller_id)
        .where(Product.is_active == 1)
        .where(Product.stok <= threshold)
        .order_by(Product.stok.asc())
        .limit(20)
    )
    low = r.scalars().all()
    items = [{"product_id": p.id, "nama": p.nama, "stok": p.stok} for p in low]
    if items:
        db.add(AgentRun(
            seller_id=seller_id, agent_role="inventory", trigger="cron", status="done",
            summary=f"{len(items)} produk stok menipis (≤{threshold})",
            detail_json={"items": items},
        ))
        await db.flush()
    return items
```

### 4B. Finance — buat `backend/services/agent_os/finance.py`
```python
"""JUALIN OS — Keuangan AI (Finance)."""
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.order import Order

PAID_STATUSES = {"paid", "processing", "shipped", "delivered", "done"}


def _status_str(o) -> str:
    return o.status.value if hasattr(o.status, "value") else str(o.status)


async def build_finance_snapshot(seller_id: int, db: AsyncSession) -> dict:
    """Snapshot keuangan hari ini vs kemarin. Hanya membaca (tidak menulis)."""
    now = datetime.now(timezone.utc)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_yest = start_today - timedelta(days=1)

    r = await db.execute(
        select(Order).where(Order.seller_id == seller_id).where(Order.created_at >= start_yest)
    )
    orders = r.scalars().all()

    def bucket(o):
        return "today" if o.created_at and o.created_at >= start_today else "yest"

    today = [o for o in orders if bucket(o) == "today"]
    yest = [o for o in orders if bucket(o) == "yest"]

    def revenue(lst):
        return sum(float(o.total or 0) for o in lst if _status_str(o) in PAID_STATUSES)

    rev_today = revenue(today)
    rev_yest = revenue(yest)
    pending = [o for o in today if _status_str(o) == "pending"]
    pending_value = sum(float(o.total or 0) for o in pending)

    # Produk terlaris hari ini (dari items)
    counter = {}
    for o in today:
        if _status_str(o) not in PAID_STATUSES:
            continue
        for it in (o.items if isinstance(o.items, list) else []):
            nama = it.get("nama", "?")
            counter[nama] = counter.get(nama, 0) + int(it.get("qty", 1))
    top_product = max(counter.items(), key=lambda kv: kv[1])[0] if counter else None

    delta_pct = 0.0 if rev_yest <= 0 else round((rev_today - rev_yest) / rev_yest * 100, 1)
    return {
        "revenue_today": round(rev_today),
        "revenue_yesterday": round(rev_yest),
        "revenue_delta_pct": delta_pct,
        "orders_today": len(today),
        "paid_today": len([o for o in today if _status_str(o) in PAID_STATUSES]),
        "pending_today": len(pending),
        "pending_value": round(pending_value),
        "top_product": top_product,
    }
```

### 4C. Growth — buat `backend/services/agent_os/growth.py`
```python
"""JUALIN OS — Marketing AI (Growth): identifikasi peluang proaktif."""
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging_config import get_logger
from models.order import Order, OrderStatus
from models.crm import Customer
from models.agent_os import AgentRun

logger = get_logger(__name__)


async def run_growth_cycle(seller_id: int, db: AsyncSession, policy) -> dict:
    """
    Identifikasi (1) pembayaran tertunda yang perlu ditagih, (2) pelanggan pasif untuk win-back.
    Catat AgentRun bila ada temuan. Tidak mengirim pesan (aman tanpa kredensial WA).
    """
    now = datetime.now(timezone.utc)

    # 1. Pending payment > 1 jam
    cutoff = now - timedelta(hours=1)
    r = await db.execute(
        select(Order)
        .where(Order.seller_id == seller_id)
        .where(Order.status == OrderStatus.PENDING)
        .where(Order.created_at <= cutoff)
        .order_by(Order.created_at.asc())
        .limit(20)
    )
    pending = r.scalars().all()
    pending_value = sum(float(o.total or 0) for o in pending)

    # 2. Pelanggan pasif (last_seen > 14 hari, pernah order)
    inactive_cut = now - timedelta(days=14)
    r2 = await db.execute(
        select(Customer)
        .where(Customer.seller_id == seller_id)
        .where(Customer.total_orders > 0)
        .where(Customer.last_seen_at != None)  # noqa: E711
        .where(Customer.last_seen_at <= inactive_cut)
        .limit(20)
    )
    inactive = r2.scalars().all()

    findings = {
        "pending_orders": len(pending),
        "pending_value": round(pending_value),
        "winback_candidates": len(inactive),
    }

    if pending or inactive:
        db.add(AgentRun(
            seller_id=seller_id, agent_role="growth", trigger="cron", status="done",
            summary=(f"{len(pending)} pembayaran tertunda (Rp {pending_value:,.0f}) perlu ditagih, "
                     f"{len(inactive)} pelanggan pasif bisa di-win-back"),
            detail_json=findings,
        ))
        await db.flush()
    return findings
```

### 4D. Brief (Laporan Harian) — buat `backend/services/agent_os/brief.py`
```python
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
```

### 4E. Cycles (untuk worker) — buat `backend/services/agent_os/cycles.py`
```python
"""JUALIN OS — Siklus proaktif untuk worker arq (dipanggil cron)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging_config import get_logger
from models.user import User, UserRole
from services.agent_os.policy import get_or_create_policy
from services.agent_os.inventory import scan_low_stock
from services.agent_os.growth import run_growth_cycle

logger = get_logger(__name__)


async def run_all_seller_cycles(db: AsyncSession) -> dict:
    """Jalankan inventory scan + growth cycle untuk setiap seller. Commit di sini."""
    r = await db.execute(select(User).where(User.role == UserRole.SELLER))
    sellers = r.scalars().all()
    processed = 0
    for seller in sellers:
        try:
            policy = await get_or_create_policy(seller.id, db)
            if policy.allow_low_stock_alert:
                await scan_low_stock(seller.id, db, policy.low_stock_threshold)
            if policy.allow_auto_followup:
                await run_growth_cycle(seller.id, db, policy)
            await db.commit()
            processed += 1
        except Exception as e:
            await db.rollback()
            logger.warning(f"cycle failed for seller {seller.id}: {e}")
    return {"sellers_processed": processed}
```

**Verifikasi 4:** Backend harus tetap bisa di-import tanpa error:
```powershell
cd backend ; .\venv\Scripts\activate ; python -c "import services.agent_os.inventory, services.agent_os.finance, services.agent_os.growth, services.agent_os.brief, services.agent_os.cycles; print('OK import agent_os services')"
```
Harus mencetak `OK import agent_os services`.

---

## FASE 5 — Orchestrator & integrasi ke chat

### 5A. Orchestrator — buat `backend/services/agent_os/orchestrator.py`
```python
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
    db.add(AgentRun(
        seller_id=seller_id, agent_role="sales", trigger="chat", status="done",
        summary=summary, detail_json={"intent": intent, "stage": sales_stage, "order_created": order_created},
        conversation_id=conversation_id,
    ))
    await db.flush()
```

### 5B. Integrasi ke `backend/api/routes_chat.py`
Lakukan **3 sisipan kecil** (jangan ubah logika lain).

**Edit 5B.1 — tambah init flag.** Cari blok inisialisasi (sekitar baris 350-356):
```python
    intent = "general"
    sales_stage = "greeting"
    response_start = time.monotonic()
    order_created = False
    ai_response_text = ""
    structured_used = False
```
**Ganti** menjadi (tambah satu baris terakhir):
```python
    intent = "general"
    sales_stage = "greeting"
    response_start = time.monotonic()
    order_created = False
    ai_response_text = ""
    structured_used = False
    agent_os_handled = False
```

**Edit 5B.2 — sisipkan hook orchestrator.** TEPAT setelah baris `structured_used = False` (dan `agent_os_handled = False`) yang baru, dan **SEBELUM** baris komentar `# ── Try structured AI actions first if enabled ──`, sisipkan:
```python
    # ── JUALIN OS: orkestrasi multi-agen (negosiasi dll.) ──
    if settings.ENABLE_AGENT_OS:
        try:
            from services.agent_os.orchestrator import agent_os_handle_turn
            os_result = await agent_os_handle_turn(
                seller=seller, conversation=conversation, message=req.message,
                history=history, db=db, memory_context=memory_context,
            )
            if os_result.get("handled"):
                ai_response_text = os_result["reply"]
                intent = os_result.get("intent", intent)
                sales_stage = os_result.get("stage", sales_stage)
                order_created = os_result.get("order_created", order_created)
                structured_used = True      # cegah parser order lama berjalan
                agent_os_handled = True
        except Exception as e:
            logger.warning(f"Agent OS turn skipped: {e}")
```

**Edit 5B.3 — guard blok structured lama.** Cari baris:
```python
    # ── Try structured AI actions first if enabled ──
    if settings.ENABLE_AI_ACTIONS:
```
**Ganti** baris `if` menjadi:
```python
    # ── Try structured AI actions first if enabled ──
    if settings.ENABLE_AI_ACTIONS and not ai_response_text:
```

**Edit 5B.4 — catat aktivitas Sales sebelum commit.** Cari baris (sekitar 470):
```python
    await db.commit()
    
    return ChatResponse(
        response=ai_response_text,
        session_id=session_id,
        conversation_id=conversation.id,
    )
```
**Tepat sebelum** `await db.commit()`, sisipkan:
```python
    # ── JUALIN OS: catat aktivitas Pramuniaga untuk activity feed ──
    if settings.ENABLE_AGENT_OS and not agent_os_handled:
        try:
            from services.agent_os.orchestrator import record_sales_activity
            await record_sales_activity(seller.id, conversation.id, intent, sales_stage, order_created, db)
        except Exception:
            pass

```

**Verifikasi 5:** Start backend (`uvicorn main:app --reload`), lalu jalankan tes chat negosiasi via curl (PowerShell):
```powershell
# pesan 1: tanya produk dulu (biar konteks ada)
curl.exe -s -X POST http://localhost:8000/api/chat/send -H "Content-Type: application/json" -d "{\"message\":\"kak ada Dress Emerald Elegan?\",\"seller_slug\":\"toko-sari-fashion\",\"session_id\":\"nego-demo-1\"}"
# pesan 2: nego
curl.exe -s -X POST http://localhost:8000/api/chat/send -H "Content-Type: application/json" -d "{\"message\":\"boleh 150 ribu kak?\",\"seller_slug\":\"toko-sari-fashion\",\"session_id\":\"nego-demo-1\"}"
```
**Harapan:** balasan pesan 2 berisi penawaran harga yang **bukan** 150.000 dan **tidak di bawah floor** (mis. menawarkan ~Rp 175.000). Cek juga tabel `agent_runs` punya baris baru:
```powershell
docker compose exec db psql -U postgres -d jualin_ai -c "SELECT agent_role, summary FROM agent_runs ORDER BY id DESC LIMIT 5;"
```
Harus ada baris `negotiator`. **Stop uvicorn.**

> ⚠️ Catatan: pada DB demo, `cost_price` produk masih 0 → floor dihitung dari diskon maks saja (189000×0.85 = 160.650). FASE 10 akan mengisi `cost_price` agar floor berbasis margin nyata. Negosiasi tetap aman di kedua kondisi.

---

## FASE 6 — Worker cron (kerja proaktif)

### 6A. Edit `backend/worker.py`
**Edit 6A.1 — tambah fungsi cron.** Setelah fungsi `cron_workflow_tick` (cari `async def cron_workflow_tick`), tambahkan fungsi baru di bawahnya:
```python
# ══════════════════════════════════════════════════
# Cron: JUALIN OS Tick (proaktif multi-agen)
# ══════════════════════════════════════════════════

async def cron_agent_os_tick(ctx):
    """Jalankan siklus proaktif (inventory scan + growth) untuk semua seller."""
    if not settings.ENABLE_AGENT_OS:
        return
    try:
        from services.agent_os.cycles import run_all_seller_cycles
        async with async_session() as db:
            result = await run_all_seller_cycles(db)
            logger.info("Agent OS tick done", extra=result)
    except Exception as e:
        logger.error(f"Agent OS tick error: {e}", exc_info=True)
```

**Edit 6A.2 — daftarkan ke cron_jobs.** Cari list `cron_jobs = [` di dalam `class WorkerSettings`. Sebelum baris penutup `]`, tambahkan:
```python
        # JUALIN OS proaktif setiap 10 menit
        cron(cron_agent_os_tick, minute={0, 10, 20, 30, 40, 50}, unique=True),
```

**Verifikasi 6:** Import worker tanpa error:
```powershell
cd backend ; .\venv\Scripts\activate ; python -c "import worker; print('worker OK', [c for c in dir(worker) if c.startswith('cron_')])"
```
Harus memuat `cron_agent_os_tick`. *(Tidak perlu menjalankan worker untuk demo; cron opsional.)*

---

## FASE 7 — API `/api/agent-os/*`

### 7A. Buat `backend/api/routes_agent_os.py`
```python
"""JUALIN OS — API routes untuk Pusat Komando AI Crew."""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import get_db
from models.user import User
from models.agent_os import AgentPolicy, AgentRun, AgentApproval, NegotiationState, AGENT_ROLES
from api.routes_auth import get_current_user
from core.audit import record_audit
from services.agent_os.policy import get_or_create_policy
from services.agent_os.finance import build_finance_snapshot
from services.agent_os.brief import build_daily_brief

router = APIRouter()


def _run_dict(r: AgentRun) -> dict:
    return {
        "id": r.id, "agent_role": r.agent_role, "trigger": r.trigger, "status": r.status,
        "summary": r.summary, "detail": r.detail_json or {},
        "conversation_id": r.conversation_id, "order_id": r.order_id,
        "created_at": r.created_at.isoformat() if r.created_at else "",
    }


@router.get("/overview")
async def overview(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    r = await db.execute(
        select(AgentRun.agent_role, func.count(AgentRun.id))
        .where(AgentRun.seller_id == current_user.id)
        .where(AgentRun.created_at >= since)
        .group_by(AgentRun.agent_role)
    )
    by_role = {role: int(cnt) for role, cnt in r.all()}

    pa = await db.execute(
        select(func.count(AgentApproval.id))
        .where(AgentApproval.seller_id == current_user.id)
        .where(AgentApproval.status == "pending")
    )
    pending_approvals = int(pa.scalar() or 0)

    finance = await build_finance_snapshot(current_user.id, db)

    crew = []
    labels = {
        "orchestrator": "Manajer AI", "sales": "Pramuniaga", "negotiator": "Juru Tawar",
        "inventory": "Gudang", "growth": "Marketing", "finance": "Keuangan", "cs": "Layanan",
    }
    for role in AGENT_ROLES:
        crew.append({
            "role": role, "label": labels.get(role, role),
            "actions_24h": by_role.get(role, 0),
            "active": True,
        })
    return {
        "crew": crew,
        "activity_by_role": by_role,
        "pending_approvals": pending_approvals,
        "finance": finance,
    }


@router.get("/activity")
async def activity(limit: int = 30, current_user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    limit = max(1, min(limit, 100))
    r = await db.execute(
        select(AgentRun).where(AgentRun.seller_id == current_user.id)
        .order_by(desc(AgentRun.id)).limit(limit)
    )
    return [_run_dict(x) for x in r.scalars().all()]


@router.get("/brief")
async def brief(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    data = await build_daily_brief(current_user.id, db)
    await db.commit()
    return data


@router.get("/policy")
async def get_policy(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = await get_or_create_policy(current_user.id, db)
    await db.commit()
    return {
        "autonomy_level": p.autonomy_level,
        "allow_auto_negotiation": p.allow_auto_negotiation,
        "allow_auto_followup": p.allow_auto_followup,
        "allow_low_stock_alert": p.allow_low_stock_alert,
        "daily_brief_enabled": p.daily_brief_enabled,
        "max_discount_percent": p.max_discount_percent,
        "margin_floor_percent": p.margin_floor_percent,
        "require_approval_above_percent": p.require_approval_above_percent,
        "nego_max_rounds": p.nego_max_rounds,
        "low_stock_threshold": p.low_stock_threshold,
    }


class PolicyUpdate(BaseModel):
    autonomy_level: str | None = None
    allow_auto_negotiation: bool | None = None
    allow_auto_followup: bool | None = None
    allow_low_stock_alert: bool | None = None
    daily_brief_enabled: bool | None = None
    max_discount_percent: float | None = None
    margin_floor_percent: float | None = None
    require_approval_above_percent: float | None = None
    nego_max_rounds: int | None = None
    low_stock_threshold: int | None = None


@router.patch("/policy")
async def update_policy(body: PolicyUpdate, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    p = await get_or_create_policy(current_user.id, db)
    if body.autonomy_level is not None:
        if body.autonomy_level not in ("assist", "auto_with_approval", "full_auto"):
            raise HTTPException(status_code=400, detail="autonomy_level tidak valid")
        p.autonomy_level = body.autonomy_level
    for field in ("allow_auto_negotiation", "allow_auto_followup", "allow_low_stock_alert", "daily_brief_enabled"):
        val = getattr(body, field)
        if val is not None:
            setattr(p, field, bool(val))
    for field, lo, hi in (("max_discount_percent", 0, 90), ("margin_floor_percent", 0, 90),
                          ("require_approval_above_percent", 0, 90)):
        val = getattr(body, field)
        if val is not None:
            setattr(p, field, max(lo, min(float(val), hi)))
    if body.nego_max_rounds is not None:
        p.nego_max_rounds = max(1, min(int(body.nego_max_rounds), 6))
    if body.low_stock_threshold is not None:
        p.low_stock_threshold = max(0, min(int(body.low_stock_threshold), 100))
    await db.commit()
    return {"success": True}


@router.get("/approvals")
async def list_approvals(status: str = "pending", current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    q = select(AgentApproval).where(AgentApproval.seller_id == current_user.id)
    if status:
        q = q.where(AgentApproval.status == status)
    q = q.order_by(desc(AgentApproval.id)).limit(50)
    r = await db.execute(q)
    return [
        {
            "id": a.id, "agent_role": a.agent_role, "action_type": a.action_type,
            "title": a.title, "detail": a.detail_json or {}, "status": a.status,
            "conversation_id": a.conversation_id,
            "created_at": a.created_at.isoformat() if a.created_at else "",
        }
        for a in r.scalars().all()
    ]


async def _decide_approval(approval_id: int, decision: str, current_user: User, db: AsyncSession):
    r = await db.execute(
        select(AgentApproval).where(AgentApproval.id == approval_id)
        .where(AgentApproval.seller_id == current_user.id)
    )
    a = r.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Approval tidak ditemukan")
    if a.status != "pending":
        return {"success": True, "already": a.status}
    a.status = decision
    a.decided_by = current_user.id
    a.decided_at = datetime.now(timezone.utc)
    db.add(AgentRun(
        seller_id=current_user.id, agent_role="negotiator", trigger="manual", status="done",
        summary=f"Persetujuan {decision}: {a.title}", detail_json={"approval_id": a.id},
        conversation_id=a.conversation_id,
    ))
    await record_audit(
        db, action=f"agent_os.approval.{decision}", entity_type="agent_approval",
        entity_id=a.id, seller_id=current_user.id, actor_user_id=current_user.id, actor_type="seller",
        after={"title": a.title},
    )
    await db.commit()
    return {"success": True, "status": a.status}


@router.post("/approvals/{approval_id}/approve")
async def approve(approval_id: int, current_user: User = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    return await _decide_approval(approval_id, "approved", current_user, db)


@router.post("/approvals/{approval_id}/reject")
async def reject(approval_id: int, current_user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    return await _decide_approval(approval_id, "rejected", current_user, db)


@router.get("/negotiations")
async def negotiations(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(NegotiationState).where(NegotiationState.seller_id == current_user.id)
        .order_by(desc(NegotiationState.id)).limit(30)
    )
    return [
        {
            "id": s.id, "conversation_id": s.conversation_id, "product_id": s.product_id,
            "list_price": s.list_price, "floor_price": s.floor_price, "current_offer": s.current_offer,
            "last_customer_ask": s.last_customer_ask, "rounds": s.rounds, "status": s.status,
            "history": s.history_json or [],
        }
        for s in r.scalars().all()
    ]
```

### 7B. Mount router — edit `backend/main.py`
**Edit 7B.1 — import.** Cari baris:
```python
from api.routes_wa_templates import router as wa_templates_router
```
**Tepat di bawahnya** tambahkan:
```python
from api.routes_agent_os import router as agent_os_router
```
**Edit 7B.2 — include.** Cari baris:
```python
app.include_router(wa_templates_router, prefix="/api/whatsapp", tags=["WhatsApp Templates"])
```
**Tepat di bawahnya** tambahkan:
```python

# JUALIN OS router
app.include_router(agent_os_router, prefix="/api/agent-os", tags=["Agent OS"])
```

**Verifikasi 7:** Start backend. Login demo lalu panggil overview:
```powershell
# ambil token
$tok = (curl.exe -s -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d "{\"email\":\"demo@jualin.ai\",\"password\":\"demo123\"}" | ConvertFrom-Json).access_token
curl.exe -s http://localhost:8000/api/agent-os/overview -H "Authorization: Bearer $tok"
```
Harus mengembalikan JSON dengan `crew` (7 agen) + `finance`. **Stop uvicorn.**

---

## FASE 8 — Frontend: helper API + nav

### 8A. Edit `frontend/lib/api.js`
**Edit 8A.1** Di dalam objek `export const api = { ... }`, sebelum kurung tutup `};` (cari blok terakhir `// ── Market Acceptance: Sprint 8 — Concierge ──` lalu setelah `getImpersonationToken`), tambahkan **sebelum** `};` penutup objek:
```javascript

  // ── JUALIN OS: Agent OS / AI Crew ──
  agentOsOverview: () => fetchAPI("/api/agent-os/overview"),
  agentOsActivity: (limit = 30) => fetchAPI(`/api/agent-os/activity?limit=${limit}`),
  agentOsBrief: () => fetchAPI("/api/agent-os/brief"),
  agentOsGetPolicy: () => fetchAPI("/api/agent-os/policy"),
  agentOsUpdatePolicy: (body) =>
    fetchAPI("/api/agent-os/policy", { method: "PATCH", body: JSON.stringify(body) }),
  agentOsApprovals: (status = "pending") =>
    fetchAPI(`/api/agent-os/approvals?status=${status}`),
  agentOsApprove: (id) =>
    fetchAPI(`/api/agent-os/approvals/${id}/approve`, { method: "POST" }),
  agentOsReject: (id) =>
    fetchAPI(`/api/agent-os/approvals/${id}/reject`, { method: "POST" }),
  agentOsNegotiations: () => fetchAPI("/api/agent-os/negotiations"),
```
> ⚠️ Pastikan masuk DI DALAM objek `api` (sebelum `};`), bukan setelahnya.

### 8B. Edit `frontend/app/dashboard/layout.js`
**Edit 8B.1** Pada array `sellerNavItems`, setelah item Overview:
```javascript
  { href: "/dashboard", icon: "📊", label: "Overview" },
```
**tambahkan tepat di bawahnya:**
```javascript
  { href: "/dashboard/agent-os", icon: "🤖", label: "AI Crew" },
```
**Edit 8B.2** Pada array `adminNavItems`, cari item `{ href: "/dashboard", icon: "🏪", label: "Toko Saya", divider: true },` dan **tepat di bawahnya** tambahkan:
```javascript
  { href: "/dashboard/agent-os", icon: "🤖", label: "AI Crew" },
```

---

## FASE 9 — Frontend: halaman Pusat Komando AI Crew

Buat file `frontend/app/dashboard/agent-os/page.js`. Halaman ini memakai **inline style** (tanpa CSS module) agar mandiri. Tiru pola `"use client"` dari halaman dashboard lain.

```javascript
"use client";
import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

const ROLE_EMOJI = {
  orchestrator: "🧭", sales: "🛍️", negotiator: "🤝",
  inventory: "📦", growth: "📣", finance: "💰", cs: "🎧",
};

function rupiah(n) {
  return "Rp " + Number(n || 0).toLocaleString("id-ID");
}

export default function AgentOsPage() {
  const [overview, setOverview] = useState(null);
  const [activity, setActivity] = useState([]);
  const [brief, setBrief] = useState(null);
  const [approvals, setApprovals] = useState([]);
  const [negotiations, setNegotiations] = useState([]);
  const [policy, setPolicy] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setError("");
      const [ov, act, appr, neg, pol] = await Promise.all([
        api.agentOsOverview(),
        api.agentOsActivity(40),
        api.agentOsApprovals("pending"),
        api.agentOsNegotiations(),
        api.agentOsGetPolicy(),
      ]);
      setOverview(ov);
      setActivity(act);
      setApprovals(appr);
      setNegotiations(neg);
      setPolicy(pol);
    } catch (e) {
      setError(e.message || "Gagal memuat");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 8000); // live refresh feed
    return () => clearInterval(t);
  }, [load]);

  const loadBrief = async () => {
    try {
      const b = await api.agentOsBrief();
      setBrief(b);
    } catch (e) {
      setError(e.message);
    }
  };

  const decide = async (id, action) => {
    try {
      if (action === "approve") await api.agentOsApprove(id);
      else await api.agentOsReject(id);
      await load();
    } catch (e) {
      setError(e.message);
    }
  };

  const savePolicy = async (patch) => {
    try {
      const next = { ...policy, ...patch };
      setPolicy(next);
      await api.agentOsUpdatePolicy(patch);
    } catch (e) {
      setError(e.message);
    }
  };

  if (loading) return <div style={{ padding: 24, color: "#94a3b8" }}>Memuat AI Crew…</div>;

  const card = {
    background: "#0f172a", border: "1px solid #1e293b", borderRadius: 14,
    padding: 16, color: "#e2e8f0",
  };
  const chip = (bg) => ({
    display: "inline-block", padding: "2px 8px", borderRadius: 999,
    fontSize: 11, fontWeight: 700, background: bg, color: "#0b1220",
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Header */}
      <div style={{ ...card, background: "linear-gradient(135deg,#0b3b2e,#0f172a)" }}>
        <h2 style={{ margin: 0, fontSize: 22 }}>🤖 AI Crew — Pusat Komando Toko Otonom</h2>
        <p style={{ margin: "6px 0 0", color: "#94a3b8" }}>
          Tim karyawan AI yang menjalankan tokomu. Semua tindakan tercatat & bisa kamu kendalikan.
        </p>
      </div>

      {error && <div style={{ ...card, borderColor: "#7f1d1d", color: "#fecaca" }}>{error}</div>}

      {/* KPI ringkas */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 12 }}>
        <div style={card}>
          <div style={{ color: "#94a3b8", fontSize: 12 }}>Omzet hari ini</div>
          <div style={{ fontSize: 22, fontWeight: 800 }}>{rupiah(overview?.finance?.revenue_today)}</div>
          <div style={{ fontSize: 12, color: (overview?.finance?.revenue_delta_pct ?? 0) >= 0 ? "#34d399" : "#f87171" }}>
            {overview?.finance?.revenue_delta_pct ?? 0}% vs kemarin
          </div>
        </div>
        <div style={card}>
          <div style={{ color: "#94a3b8", fontSize: 12 }}>Pembayaran tertunda</div>
          <div style={{ fontSize: 22, fontWeight: 800 }}>{overview?.finance?.pending_today ?? 0}</div>
          <div style={{ fontSize: 12, color: "#fbbf24" }}>{rupiah(overview?.finance?.pending_value)}</div>
        </div>
        <div style={card}>
          <div style={{ color: "#94a3b8", fontSize: 12 }}>Menunggu persetujuan</div>
          <div style={{ fontSize: 22, fontWeight: 800 }}>{overview?.pending_approvals ?? 0}</div>
        </div>
        <div style={card}>
          <div style={{ color: "#94a3b8", fontSize: 12 }}>Produk terlaris</div>
          <div style={{ fontSize: 16, fontWeight: 700 }}>{overview?.finance?.top_product || "-"}</div>
        </div>
      </div>

      {/* Crew cards */}
      <div style={card}>
        <h3 style={{ marginTop: 0 }}>Tim Agen</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 10 }}>
          {(overview?.crew || []).map((c) => (
            <div key={c.role} style={{ background: "#111c33", borderRadius: 12, padding: 12, textAlign: "center" }}>
              <div style={{ fontSize: 26 }}>{ROLE_EMOJI[c.role] || "🤖"}</div>
              <div style={{ fontWeight: 700, marginTop: 4 }}>{c.label}</div>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>{c.actions_24h} aksi / 24 jam</div>
              <span style={chip("#34d399")}>aktif</span>
            </div>
          ))}
        </div>
      </div>

      {/* Approvals */}
      <div style={card}>
        <h3 style={{ marginTop: 0 }}>🔔 Menunggu Persetujuan Kamu ({approvals.length})</h3>
        {approvals.length === 0 && <div style={{ color: "#94a3b8" }}>Tidak ada yang perlu disetujui. 👍</div>}
        {approvals.map((a) => (
          <div key={a.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "10px 0", borderBottom: "1px solid #1e293b" }}>
            <div>
              <div style={{ fontWeight: 700 }}>{a.title}</div>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>{a.action_type} · {a.agent_role}</div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={() => decide(a.id, "approve")}
                style={{ background: "#22c55e", border: 0, color: "#06210f", fontWeight: 700, padding: "8px 14px", borderRadius: 8, cursor: "pointer" }}>
                Setujui
              </button>
              <button onClick={() => decide(a.id, "reject")}
                style={{ background: "#334155", border: 0, color: "#e2e8f0", padding: "8px 14px", borderRadius: 8, cursor: "pointer" }}>
                Tolak
              </button>
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Activity feed */}
        <div style={card}>
          <h3 style={{ marginTop: 0 }}>📡 Aktivitas Agen (live)</h3>
          <div style={{ maxHeight: 360, overflowY: "auto" }}>
            {activity.length === 0 && <div style={{ color: "#94a3b8" }}>Belum ada aktivitas.</div>}
            {activity.map((r) => (
              <div key={r.id} style={{ display: "flex", gap: 10, padding: "8px 0", borderBottom: "1px solid #1e293b" }}>
                <div style={{ fontSize: 20 }}>{ROLE_EMOJI[r.agent_role] || "🤖"}</div>
                <div>
                  <div style={{ fontSize: 13 }}>{r.summary}</div>
                  <div style={{ fontSize: 11, color: "#64748b" }}>
                    {r.agent_role} · {r.trigger} · {r.created_at?.slice(11, 19)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Negotiations */}
        <div style={card}>
          <h3 style={{ marginTop: 0 }}>🤝 Negosiasi Berjalan</h3>
          <div style={{ maxHeight: 360, overflowY: "auto" }}>
            {negotiations.length === 0 && <div style={{ color: "#94a3b8" }}>Belum ada negosiasi.</div>}
            {negotiations.map((n) => (
              <div key={n.id} style={{ padding: "8px 0", borderBottom: "1px solid #1e293b", fontSize: 13 }}>
                <div>Normal {rupiah(n.list_price)} · Lantai {rupiah(n.floor_price)}</div>
                <div>Penawaran terakhir: <b>{rupiah(n.current_offer)}</b> · {n.rounds} ronde · <span style={chip(
                  n.status === "accepted" ? "#34d399" : n.status === "escalated" ? "#fbbf24" : "#60a5fa"
                )}>{n.status}</span></div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Daily brief */}
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>🗞️ Laporan Harian Manajer AI</h3>
          <button onClick={loadBrief}
            style={{ background: "#22c55e", border: 0, color: "#06210f", fontWeight: 700, padding: "8px 14px", borderRadius: 8, cursor: "pointer" }}>
            Buat / Refresh Laporan
          </button>
        </div>
        {brief ? (
          <p style={{ marginTop: 12, lineHeight: 1.6 }}>{brief.narrative}</p>
        ) : (
          <p style={{ color: "#94a3b8" }}>Klik tombol untuk menghasilkan laporan hari ini.</p>
        )}
      </div>

      {/* Policy */}
      {policy && (
        <div style={card}>
          <h3 style={{ marginTop: 0 }}>⚙️ Kebijakan & Kendali</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12 }}>
            <label style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>Negosiasi otomatis</span>
              <input type="checkbox" checked={!!policy.allow_auto_negotiation}
                onChange={(e) => savePolicy({ allow_auto_negotiation: e.target.checked })} />
            </label>
            <label style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>Diskon maksimum (%)</span>
              <input type="number" value={policy.max_discount_percent}
                onChange={(e) => setPolicy({ ...policy, max_discount_percent: e.target.value })}
                onBlur={(e) => savePolicy({ max_discount_percent: Number(e.target.value) })}
                style={{ width: 70 }} />
            </label>
            <label style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>Margin minimum (%)</span>
              <input type="number" value={policy.margin_floor_percent}
                onChange={(e) => setPolicy({ ...policy, margin_floor_percent: e.target.value })}
                onBlur={(e) => savePolicy({ margin_floor_percent: Number(e.target.value) })}
                style={{ width: 70 }} />
            </label>
            <label style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>Butuh approval di atas (%)</span>
              <input type="number" value={policy.require_approval_above_percent}
                onChange={(e) => setPolicy({ ...policy, require_approval_above_percent: e.target.value })}
                onBlur={(e) => savePolicy({ require_approval_above_percent: Number(e.target.value) })}
                style={{ width: 70 }} />
            </label>
          </div>
        </div>
      )}
    </div>
  );
}
```

**Verifikasi 9:** Jalankan frontend + backend, buka `http://localhost:3000/dashboard/agent-os` (login demo). Halaman harus tampil: KPI, 7 kartu agen, feed aktivitas, dll. (Feed terisi setelah ada chat — lihat Fase 11.)
```powershell
# tab 1
cd backend ; .\venv\Scripts\activate ; uvicorn main:app --reload
# tab 2
cd frontend ; npm run dev
```

---

## FASE 10 — Seed: cost_price + policy demo

Buat `backend/seed/seed_agent_os.py`:
```python
"""
Seed tambahan JUALIN OS:
- Isi cost_price produk demo (≈60% harga) agar negosiasi berbasis margin nyata.
- Buat AgentPolicy untuk demo seller.

Jalankan SETELAH seed_data:  python -m seed.seed_agent_os
"""
import asyncio
import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from models.database import async_session, init_db
from models.user import User
from models.product import Product
from models.agent_os import AgentPolicy


async def run():
    await init_db()
    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == "demo@jualin.ai"))
        seller = result.scalar_one_or_none()
        if not seller:
            print("⚠️ Demo seller belum ada. Jalankan `python -m seed.seed_data` dulu.")
            return

        # 1. cost_price = 60% harga (kalau masih 0)
        pr = await db.execute(select(Product).where(Product.seller_id == seller.id))
        updated = 0
        for p in pr.scalars().all():
            if not getattr(p, "cost_price", 0):
                p.cost_price = round(float(p.harga) * 0.6)
                updated += 1

        # 2. AgentPolicy
        pol = (await db.execute(
            select(AgentPolicy).where(AgentPolicy.seller_id == seller.id)
        )).scalar_one_or_none()
        if not pol:
            db.add(AgentPolicy(seller_id=seller.id))
            print("✅ AgentPolicy demo dibuat")

        await db.commit()
        print(f"✅ cost_price diisi untuk {updated} produk. JUALIN OS siap didemokan.")


if __name__ == "__main__":
    asyncio.run(run())
```

**Verifikasi 10:**
```powershell
cd backend ; .\venv\Scripts\activate ; python -m seed.seed_agent_os
```
Harus mencetak `✅ cost_price diisi untuk N produk`. Cek:
```powershell
docker compose exec db psql -U postgres -d jualin_ai -c "SELECT nama, harga, cost_price FROM products LIMIT 5;"
```
Kolom `cost_price` harus terisi (bukan 0).

---

## FASE 11 — Verifikasi end-to-end & Skrip Demo

### 11A. Uji alur lengkap (curl)
Pastikan backend + frontend jalan & seed_agent_os sudah dijalankan.

```powershell
$base = "http://localhost:8000"
$slug = "toko-sari-fashion"
$sid  = "demo-judge-1"

# 1) Tanya produk
curl.exe -s -X POST $base/api/chat/send -H "Content-Type: application/json" -d "{\"message\":\"kak Dress Emerald Elegan ready?\",\"seller_slug\":\"$slug\",\"session_id\":\"$sid\"}"
# 2) Nego wajar (di atas floor) → harus di-counter, TIDAK rugi
curl.exe -s -X POST $base/api/chat/send -H "Content-Type: application/json" -d "{\"message\":\"boleh 150 ribu kak?\",\"seller_slug\":\"$slug\",\"session_id\":\"$sid\"}"
# 3) Nego sadis (di bawah floor) → harus counter_floor (harga terbaik, tetap >= floor)
curl.exe -s -X POST $base/api/chat/send -H "Content-Type: application/json" -d "{\"message\":\"90 ribu deh ya kak final\",\"seller_slug\":\"$slug\",\"session_id\":\"$sid\"}"
```
**Kriteria lulus:** tidak ada balasan yang menawarkan harga **< cost_price×1.1** (modal Dress Emerald = 189000×0.6 = 113400 → floor = max(113400×1.1=124740, 189000×0.85=160650) = **160650**). Jadi tidak boleh ada tawaran di bawah ~Rp 160.650.

### 11B. Cek data tercatat
```powershell
docker compose exec db psql -U postgres -d jualin_ai -c "SELECT agent_role, status, summary FROM agent_runs ORDER BY id DESC LIMIT 8;"
docker compose exec db psql -U postgres -d jualin_ai -c "SELECT product_id, list_price, floor_price, current_offer, rounds, status FROM negotiation_states ORDER BY id DESC LIMIT 3;"
```

### 11C. Skrip Demo Juri (90 detik)
1. Buka `/dashboard/agent-os` (login `demo@jualin.ai` / `demo123`). Tunjukkan **7 kartu agen** + KPI.
2. Buka tab baru ke chat publik toko: `/chat/toko-sari-fashion`. Ketik: *"Dress Emerald-nya boleh 150 ribu kak?"*
3. Tunjukkan AI **menawar balik** ke harga aman (mis. Rp 175.000), bukan menerima 150.000.
4. Kembali ke `/dashboard/agent-os` → **Activity Feed** menampilkan jejak agen **Juru Tawar** (live, auto-refresh 8 dtk) + **Negosiasi Berjalan** menampilkan list/floor/offer.
5. Ketik tawaran ekstrem (mis. *"80 ribu final ya"*) untuk memicu **counter_floor**; jika kebijakan memicu approval, tunjukkan **kartu persetujuan** → klik **Setujui**.
6. Klik **Buat Laporan** → **Laporan Harian** muncul (narasi + angka).
7. Tutup dengan **Kebijakan & Kendali**: ubah "Diskon maksimum" untuk menunjukkan penjual **pegang kendali**.

---

## KRITERIA PENERIMAAN (checklist final)

- [ ] `ENABLE_AGENT_OS=False` → aplikasi berperilaku persis seperti sebelum perubahan (chat normal, tanpa nego, tanpa feed).
- [ ] 4 tabel baru (`agent_policies`, `agent_runs`, `agent_approvals`, `negotiation_states`) terbuat; `products.cost_price` ada.
- [ ] Engine `decide_offer` **tidak pernah** mengembalikan `offer_price < floor_price` (uji Fase 3 & 11A).
- [ ] Chat dengan kata nego memicu agen Juru Tawar & membuat baris `agent_runs` (role=negotiator) + `negotiation_states`.
- [ ] Diskon di atas `require_approval_above_percent` membuat `agent_approvals` status `pending`; approve/reject berfungsi & teraudit.
- [ ] `/api/agent-os/overview|activity|brief|policy|approvals|negotiations` semua membalas 200 untuk seller login.
- [ ] Halaman `/dashboard/agent-os` tampil, KPI/feed/approval/policy berfungsi, nav "AI Crew" muncul.
- [ ] `python -m seed.seed_agent_os` mengisi cost_price + policy demo.
- [ ] Worker bisa di-import dengan `cron_agent_os_tick` (opsional untuk demo).

---

## LAMPIRAN A — Jebakan umum (HINDARI)

1. **Lupa import model di `models/__init__.py`** → tabel tidak terbuat → error "relation does not exist". (Fase 2C wajib.)
2. **Commit di tengah fungsi agent_os** → bisa memutus transaksi route chat. Selalu `flush`, biar route yang commit. (Pengecualian: `cycles.py` & endpoint API memang commit sendiri — itu benar.)
3. **`asyncio.gather` pada `db` yang sama** → crash async session. Selalu sekuensial `await`.
4. **Sisipan 5B salah urutan** → variabel `agent_os_handled` belum didefinisikan saat dipakai. Pastikan init (5B.1) ada sebelum hook (5B.2).
5. **Helper api ditaruh di luar objek `api`** → `api.agentOsOverview is not a function`. Pastikan di DALAM `{ ... }`.
6. **PowerShell**: pakai `;` bukan `&&`; pakai `curl.exe` (bukan alias `curl`) agar flag `-X`/`-d` bekerja.
7. **Next.js 16**: untuk halaman baru, jangan kreasi pola server-component/route-handler yang tak kamu lihat dipakai; tiru `"use client"` page yang ada.
8. **`o.status.value`**: Order.status adalah enum — selalu pakai helper `_status_str` yang sudah disediakan di finance.py saat membandingkan status.
9. **LLM mengarang harga**: sudah dijaga `_phrase_offer` (fallback bila angka engine tak muncul). Jangan hapus guard itu.
10. **Floor saat cost_price=0**: floor jatuh ke `harga×(1-diskon_maks)`. Tetap aman. Jalankan `seed_agent_os` agar floor berbasis margin nyata untuk demo.

---

## LAMPIRAN B — Peta jalan setelah MVP (untuk konteks, JANGAN dikerjakan dulu)

- **Agen Layanan (CS) penuh**: routing komplain + auto-handoff via `AgentApproval`.
- **Auto-resume negosiasi** setelah approval disetujui (lanjut kirim harga ke pembeli).
- **Multimodal WA-native**: voice note (STT) & gambar ("ada yang kayak gini?").
- **Auto-restock & reorder supplier** dari Inventory.
- **Reflection loop**: simpan "lesson" dari deal sukses/gagal → tuning playbook (integrasi modul `Experiment` & `AIFeedback`).
- **Brief terjadwal harian** via worker (saat ini on-demand untuk hindari spam feed).
- **Kirim aktual** growth (tagih/win-back) via WhatsApp (saat ini hanya identifikasi + approval).

---

*Dokumen ini adalah pasangan teknis dari `proposal_gemastik/PROPOSAL_JUALIN_OS_2026.md`. Kerjakan fase berurutan, verifikasi tiap fase. Selamat membangun JUALIN OS. 🤖*

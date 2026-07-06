# PLAN 2 — LLM CONTROL PANEL (ADMIN) + PENINGKATAN KUALITAS OUTPUT AGEN

> Untuk: executor coding agent. Dari: senior reviewer. Tanggal: 2026-07-06.
> **PRASYARAT: `PLAN_FINAL_HERO_PIPELINE.md` HARUS sudah dieksekusi sampai selesai.**
> Fase C plan ini mengedit `negotiation.py` versi BARU hasil plan 1. Kalau anchor tidak ketemu, cek dulu apakah plan 1 sudah jalan — jangan menebak.
>
> Isi: (A–E) admin/owner bisa mengatur LLM dari dashboard — base URL router (9Router/OpenRouter/apa pun yang OpenAI-compatible), **tumpuk banyak API key dengan rotasi + failover otomatis**, pilih model utama / model ringan / model cadangan, tombol test koneksi. (F) upgrade kualitas output tiap agen.

Aturan kerja = sama persis dengan bagian "ATURAN KERJA WAJIB" di `PLAN_FINAL_HERO_PIPELINE.md` (fase berurutan, satu commit per fase, dilarang refactor di luar plan, dilarang dependency baru, baca `frontend/AGENTS.md` sebelum edit frontend).

---

## FASE A — Model & tabel `llm_settings`

### A1. File BARU `backend/models/llm_settings.py`

```python
"""
JUALIN.AI — Konfigurasi LLM yang bisa diatur admin dari dashboard (singleton row id=1).
is_enabled=False berarti seluruh sistem memakai konfigurasi .env seperti sebelumnya (rollback aman).
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from sqlalchemy.sql import func

from models.database import Base


class LLMSettings(Base):
    __tablename__ = "llm_settings"

    id = Column(Integer, primary_key=True)          # selalu 1 (singleton)
    is_enabled = Column(Boolean, default=False, nullable=False)

    provider_label = Column(String(50), default="9router")   # label bebas utk UI
    base_url = Column(String(255), default="")                # kosong = pakai env LLM_BASE_URL
    model = Column(String(100), default="")                   # model utama (chat penjualan, brief)
    light_model = Column(String(100), default="")             # model ringan/cepat (phrasing nego); kosong = pakai model utama
    fallback_model = Column(String(100), default="")          # dicoba bila model utama gagal di semua key

    api_keys_json = Column(JSON, default=list)                # ["sk-xxx", "sk-yyy", ...] — DITUMPUK, dirotasi

    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
```

### A2. Registrasi model

Buka `backend/models/__init__.py`, tambahkan **mengikuti pola import yang sudah ada di file itu**:

```python
from models.llm_settings import LLMSettings  # noqa: F401
```

(Ini membuat `init_db()` `create_all` otomatis membuat tabelnya saat startup.)

### A3. Migrasi Alembic (untuk instalasi yang pakai alembic, idempotent)

File BARU `backend/alembic/versions/20260706_0007_llm_settings.py`:

```python
"""LLM settings singleton untuk admin control panel"""
from alembic import op
import sqlalchemy as sa

revision = "20260706_0007"
down_revision = "20260613_0006"   # ⚠️ VERIFIKASI: buka 20260613_0006_agent_os.py, salin nilai variabel `revision`-nya ke sini
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if not sa.inspect(conn).has_table("llm_settings"):
        op.create_table(
            "llm_settings",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("provider_label", sa.String(50), server_default="9router"),
            sa.Column("base_url", sa.String(255), server_default=""),
            sa.Column("model", sa.String(100), server_default=""),
            sa.Column("light_model", sa.String(100), server_default=""),
            sa.Column("fallback_model", sa.String(100), server_default=""),
            sa.Column("api_keys_json", sa.JSON, nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    op.execute("DROP TABLE IF EXISTS llm_settings")
```

**Acceptance A:** restart backend → `\dt llm_settings` ada (atau `alembic upgrade head` sukses).
**Commit:** `feat(llm): LLMSettings singleton model + migration`

---

## FASE B — Router LLM terpusat: `backend/services/llm_router.py` (file BARU)

Satu-satunya pintu keluar ke LLM. Rotasi key (sticky pada key yang berhasil), failover key→key→model cadangan→env, cache konfigurasi 60 detik.

```python
"""
JUALIN.AI — LLM Router terpusat.

Semua panggilan LLM lewat sini supaya:
1. Admin bisa ganti base URL / model / API key dari dashboard TANPA restart (cache 60 dtk).
2. API key bisa DITUMPUK: dirotasi, failover otomatis saat 401/403/429/timeout/5xx.
3. Ada tingkatan model: purpose="main" (jualan/brief) vs "light" (phrasing nego — cepat & murah).

Urutan failover per panggilan: setiap key × [model, fallback_model] → key .env sebagai cadangan terakhir.
ponytail: kursor rotasi disimpan in-memory (reset saat restart) — cukup; persist ke DB kalau nanti multi-instance.
"""
import time
from types import SimpleNamespace
from typing import AsyncGenerator

from openai import (
    AsyncOpenAI, APIConnectionError, APITimeoutError, APIStatusError,
    RateLimitError, AuthenticationError, PermissionDeniedError,
)
from sqlalchemy import select

from config import get_settings
from core.logging_config import get_logger

settings = get_settings()
logger = get_logger(__name__)

_RETRYABLE = (APIConnectionError, APITimeoutError, APIStatusError,
              RateLimitError, AuthenticationError, PermissionDeniedError)

_cfg_cache = {"cfg": None, "ts": 0.0}
_clients: dict[tuple, AsyncOpenAI] = {}
_key_cursor = 0  # sticky: mulai dari key yang terakhir sukses


def _env_cfg() -> SimpleNamespace:
    return SimpleNamespace(
        base_url=settings.LLM_BASE_URL, model=settings.LLM_MODEL,
        light_model="", fallback_model="", api_keys=[settings.LLM_API_KEY],
        source="env",
    )


def invalidate_llm_cache():
    """Panggil setelah admin mengubah settings — konfigurasi baru terpakai maksimal 1 request kemudian."""
    _cfg_cache["cfg"] = None
    _cfg_cache["ts"] = 0.0
    _clients.clear()


async def _get_cfg() -> SimpleNamespace:
    now = time.time()
    if _cfg_cache["cfg"] is not None and now - _cfg_cache["ts"] < 60:
        return _cfg_cache["cfg"]
    cfg = _env_cfg()
    try:
        from models.database import async_session
        from models.llm_settings import LLMSettings
        async with async_session() as s:
            r = await s.execute(select(LLMSettings).where(LLMSettings.id == 1))
            row = r.scalar_one_or_none()
            if row and row.is_enabled:
                keys = [k for k in (row.api_keys_json or []) if k] or [settings.LLM_API_KEY]
                cfg = SimpleNamespace(
                    base_url=row.base_url or settings.LLM_BASE_URL,
                    model=row.model or settings.LLM_MODEL,
                    light_model=row.light_model or "",
                    fallback_model=row.fallback_model or "",
                    api_keys=keys, source="db",
                )
    except Exception as e:
        logger.warning(f"llm_router: gagal baca LLMSettings, pakai env: {e}")
    _cfg_cache["cfg"] = cfg
    _cfg_cache["ts"] = now
    return cfg


def _client(base_url: str, key: str) -> AsyncOpenAI:
    ck = (base_url, key)
    if ck not in _clients:
        _clients[ck] = AsyncOpenAI(base_url=base_url, api_key=key, timeout=20.0, max_retries=0)
    return _clients[ck]


def _pick_model(cfg, purpose: str) -> str:
    if purpose == "light" and cfg.light_model:
        return cfg.light_model
    return cfg.model


def _attempts(cfg, purpose: str):
    """Generator (key_index, key, model) sesuai urutan failover."""
    n = len(cfg.api_keys)
    order = [(_key_cursor + i) % n for i in range(n)]
    primary = _pick_model(cfg, purpose)
    models = [primary]
    if cfg.fallback_model and cfg.fallback_model != primary:
        models.append(cfg.fallback_model)
    for model in models:
        for idx in order:
            yield idx, cfg.api_keys[idx], model


async def llm_chat(messages: list[dict], *, purpose: str = "main",
                   temperature: float = 0.7, max_tokens: int = 420,
                   model: str | None = None) -> str:
    """Panggilan chat non-streaming dengan rotasi key + failover. Raise bila SEMUA gagal
    (pemanggil sudah punya try/except fallback masing-masing)."""
    global _key_cursor
    cfg = await _get_cfg()
    last_err = None
    for idx, key, mdl in _attempts(cfg, purpose):
        try:
            resp = await _client(cfg.base_url, key).chat.completions.create(
                model=model or mdl, messages=messages,
                temperature=temperature, max_tokens=max_tokens,
            )
            _key_cursor = idx
            return resp.choices[0].message.content or ""
        except _RETRYABLE as e:
            last_err = e
            logger.warning(f"llm_router: key#{idx} model={model or mdl} gagal ({type(e).__name__}), coba berikutnya")
            continue
    raise last_err or RuntimeError("llm_router: tidak ada key/model yang bisa dipakai")


async def llm_chat_stream(messages: list[dict], *, purpose: str = "main",
                          temperature: float = 0.7, max_tokens: int = 420) -> AsyncGenerator[str, None]:
    """Streaming token. Failover hanya SEBELUM token pertama keluar
    (retry setelah token keluar = teks dobel di layar pembeli)."""
    global _key_cursor
    cfg = await _get_cfg()
    last_err = None
    for idx, key, mdl in _attempts(cfg, purpose):
        started = False
        try:
            stream = await _client(cfg.base_url, key).chat.completions.create(
                model=mdl, messages=messages, temperature=temperature,
                max_tokens=max_tokens, stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    started = True
                    yield chunk.choices[0].delta.content
            _key_cursor = idx
            return
        except _RETRYABLE as e:
            last_err = e
            if started:
                logger.error(f"llm_router: stream putus di tengah (key#{idx}): {e}")
                return  # jangan retry — sebagian teks sudah tampil
            logger.warning(f"llm_router: stream key#{idx} gagal sebelum token pertama, coba berikutnya")
            continue
    raise last_err or RuntimeError("llm_router: tidak ada key/model yang bisa dipakai")


async def llm_test() -> dict:
    """Untuk tombol 'Test Koneksi' di dashboard admin: coba tiap key sampai satu sukses."""
    cfg = await _get_cfg()
    t0 = time.monotonic()
    for idx, key, mdl in _attempts(cfg, "main"):
        try:
            resp = await _client(cfg.base_url, key).chat.completions.create(
                model=mdl, messages=[{"role": "user", "content": "Balas satu kata: siap"}],
                temperature=0, max_tokens=8,
            )
            return {
                "ok": True, "latency_ms": round((time.monotonic() - t0) * 1000),
                "model": mdl, "key_index": idx, "source": cfg.source,
                "reply": (resp.choices[0].message.content or "").strip()[:40],
            }
        except _RETRYABLE as e:
            last = f"{type(e).__name__}: {str(e)[:120]}"
            continue
    return {"ok": False, "error": last if 'last' in dir() else "tidak ada key", "source": cfg.source}
```

**Acceptance B:** `python -c "import asyncio; from services.llm_router import llm_test; print(asyncio.run(llm_test()))"` dari folder `backend/` → `{"ok": True, ...}` (dengan .env valid).
**Commit:** `feat(llm): central llm_router with stacked-key rotation + failover + model tiers`

---

## FASE C — Semua pemanggil LLM lewat router

### C1. `backend/ai/agent.py`

1. HAPUS blok (baris ~31-37):
```python
# LLM Client (connects to 9Router or direct API)
llm_client = AsyncOpenAI(
    base_url=settings.LLM_BASE_URL,
    api_key=settings.LLM_API_KEY,
    timeout=20.0,
    max_retries=1,
)
```
   dan HAPUS `from openai import AsyncOpenAI` di import atas.
2. Tambah import: `from services.llm_router import llm_chat, llm_chat_stream`
3. Di `get_ai_response` — GANTI:
```python
        response = await llm_client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=350,
        )
        ai_text = response.choices[0].message.content
```
   menjadi:
```python
        ai_text = await llm_chat(messages, purpose="main", temperature=0.7, max_tokens=420)
```
4. Di `get_ai_response_stream` — GANTI blok:
```python
        stream = await llm_client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=350,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_response += token
                yield {
                    "token": token,
                    "done": False,
                    "type": "token",
                }
```
   menjadi:
```python
        async for token in llm_chat_stream(messages, purpose="main", temperature=0.7, max_tokens=420):
            full_response += token
            yield {
                "token": token,
                "done": False,
                "type": "token",
            }
```
5. Di `get_ai_structured_response` — GANTI:
```python
        response = await llm_client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=0.3,  # Lower for more deterministic JSON
            max_tokens=500,
        )
        raw_text = response.choices[0].message.content
```
   menjadi:
```python
        raw_text = await llm_chat(messages, purpose="main", temperature=0.3, max_tokens=500)
```

### C2. `backend/services/agent_os/negotiation.py` (versi hasil PLAN 1)

Di `_phrase_offer`, GANTI blok try:
```python
    try:
        from ai.agent import llm_client
        resp = await llm_client.chat.completions.create(
            model=settings.LLM_MODEL, messages=prompt, temperature=0.5, max_tokens=120,
        )
        text = (resp.choices[0].message.content or "").strip()
```
menjadi:
```python
    try:
        from services.llm_router import llm_chat
        text = (await llm_chat(prompt, purpose="light", temperature=0.5, max_tokens=120)).strip()
```

### C3. `backend/services/agent_os/brief.py`

GANTI:
```python
        from ai.agent import llm_client
        ...
        resp = await llm_client.chat.completions.create(
            model=settings.LLM_MODEL, messages=prompt, temperature=0.5, max_tokens=220,
        )
        text = (resp.choices[0].message.content or "").strip()
```
menjadi:
```python
        from services.llm_router import llm_chat
        ...
        text = (await llm_chat(prompt, purpose="main", temperature=0.3, max_tokens=220)).strip()
```
(baris `prompt = [...]` di antaranya JANGAN diubah di fase ini.)

### C4. `backend/ai/llm_client.py` — delegasi (supaya onboarding/WA-template/job ikut diatur admin)

GANTI SELURUH badan fungsi `chat_completion` menjadi:
```python
async def chat_completion(
    messages: list[dict],
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """Delegasi ke llm_router terpusat (admin-configurable). Signature lama dipertahankan."""
    try:
        from services.llm_router import llm_chat
        return await llm_chat(messages, temperature=temperature, max_tokens=max_tokens, model=model)
    except Exception as e:
        logger.error(f"LLM chat completion failed: {e}", exc_info=True)
        return "Maaf kak, terjadi gangguan. Coba kirim ulang ya 😊"
```
(`get_http_client`/`close_client` biarkan — dipanggil di shutdown, tidak berbahaya.)

**Acceptance C:** grep `llm_client.chat.completions` di `backend/` → 0 hasil; chat publik tetap berfungsi; matikan internet LLM → balasan fallback tetap keluar (bukan 500).
**Commit:** `refactor(llm): all LLM calls through llm_router (single exit point)`

---

## FASE D — API Admin (append ke `backend/api/routes_admin.py`, di bagian paling bawah file)

```python
# ══════════════════════════════════════════════════
# LLM Control Panel (owner/admin platform)
# ══════════════════════════════════════════════════
from pydantic import BaseModel as _BM


def _mask_key(k: str) -> str:
    if not k:
        return ""
    return (k[:5] + "…" + k[-4:]) if len(k) > 12 else ("…" + k[-3:])


async def _get_or_create_llm_row(db: AsyncSession):
    from models.llm_settings import LLMSettings
    r = await db.execute(select(LLMSettings).where(LLMSettings.id == 1))
    row = r.scalar_one_or_none()
    if not row:
        row = LLMSettings(id=1, api_keys_json=[])
        db.add(row)
        await db.flush()
    return row


@router.get("/llm-settings")
async def get_llm_settings(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    row = await _get_or_create_llm_row(db)
    await db.commit()
    return {
        "is_enabled": row.is_enabled,
        "provider_label": row.provider_label,
        "base_url": row.base_url,
        "model": row.model,
        "light_model": row.light_model,
        "fallback_model": row.fallback_model,
        "api_keys_masked": [_mask_key(k) for k in (row.api_keys_json or [])],
        "env_fallback": {"base_url": settings.LLM_BASE_URL, "model": settings.LLM_MODEL},
    }


class LLMSettingsUpdate(_BM):
    is_enabled: bool | None = None
    provider_label: str | None = None
    base_url: str | None = None
    model: str | None = None
    light_model: str | None = None
    fallback_model: str | None = None


@router.put("/llm-settings")
async def update_llm_settings(body: LLMSettingsUpdate, admin: User = Depends(require_admin),
                              db: AsyncSession = Depends(get_db)):
    row = await _get_or_create_llm_row(db)
    if body.base_url is not None:
        b = body.base_url.strip()
        if b and not b.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="base_url harus diawali http(s)://")
        row.base_url = b
    for f in ("provider_label", "model", "light_model", "fallback_model"):
        v = getattr(body, f)
        if v is not None:
            setattr(row, f, v.strip())
    if body.is_enabled is not None:
        row.is_enabled = bool(body.is_enabled)
    await db.commit()
    from services.llm_router import invalidate_llm_cache
    invalidate_llm_cache()
    return {"success": True}


class LLMKeyAdd(_BM):
    key: str


@router.post("/llm-settings/keys")
async def add_llm_key(body: LLMKeyAdd, admin: User = Depends(require_admin),
                      db: AsyncSession = Depends(get_db)):
    key = (body.key or "").strip()
    if len(key) < 8:
        raise HTTPException(status_code=400, detail="API key terlalu pendek")
    row = await _get_or_create_llm_row(db)
    keys = list(row.api_keys_json or [])
    if key in keys:
        raise HTTPException(status_code=400, detail="Key sudah ada")
    keys.append(key)
    row.api_keys_json = keys
    await db.commit()
    from services.llm_router import invalidate_llm_cache
    invalidate_llm_cache()
    return {"success": True, "api_keys_masked": [_mask_key(k) for k in keys]}


@router.delete("/llm-settings/keys/{index}")
async def remove_llm_key(index: int, admin: User = Depends(require_admin),
                         db: AsyncSession = Depends(get_db)):
    row = await _get_or_create_llm_row(db)
    keys = list(row.api_keys_json or [])
    if index < 0 or index >= len(keys):
        raise HTTPException(status_code=404, detail="Index key tidak ada")
    keys.pop(index)
    row.api_keys_json = keys
    await db.commit()
    from services.llm_router import invalidate_llm_cache
    invalidate_llm_cache()
    return {"success": True, "api_keys_masked": [_mask_key(k) for k in keys]}


@router.post("/llm-settings/test")
async def test_llm_settings(admin: User = Depends(require_admin)):
    from services.llm_router import invalidate_llm_cache, llm_test
    invalidate_llm_cache()          # pastikan test memakai settings terbaru
    return await llm_test()
```

Catatan keamanan (WAJIB dipatuhi): key utuh TIDAK pernah dikembalikan di respons mana pun, TIDAK ditulis ke log, TIDAK dimasukkan ke audit. Kalau `record_audit` mudah dipakai di file ini, tambahkan audit `admin.llm.update` berisi field non-rahasia saja — kalau ribet, lewati.

**Acceptance D (login sebagai admin@jualin.ai):**
`GET /api/admin/llm-settings` → 200 dengan `api_keys_masked`; `POST .../keys` 2× lalu `POST .../test` → `{"ok":true, "source":"db"}` bila `is_enabled=true`; user non-admin → 403.
**Commit:** `feat(admin): LLM settings API — stacked keys, model pick, connection test`

---

## FASE E — Frontend: halaman admin `/dashboard/admin/llm`

### E1. `frontend/lib/api.js` — tambah setelah `agentOsImpact` (hasil plan 1):

```js
  // ── Admin: LLM Control Panel ──
  adminLlmGet: () => fetchAPI("/api/admin/llm-settings"),
  adminLlmUpdate: (body) =>
    fetchAPI("/api/admin/llm-settings", { method: "PUT", body: JSON.stringify(body) }),
  adminLlmAddKey: (key) =>
    fetchAPI("/api/admin/llm-settings/keys", { method: "POST", body: JSON.stringify({ key }) }),
  adminLlmRemoveKey: (index) =>
    fetchAPI(`/api/admin/llm-settings/keys/${index}`, { method: "DELETE" }),
  adminLlmTest: () =>
    fetchAPI("/api/admin/llm-settings/test", { method: "POST", body: JSON.stringify({}) }),
```

### E2. File BARU `frontend/app/dashboard/admin/llm/page.js` (komponen mandiri, gaya inline seperti halaman agent-os):

```jsx
"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const card = {
  background: "#0f172a", border: "1px solid #1e293b", borderRadius: 14,
  padding: 16, color: "#e2e8f0", marginBottom: 16,
};
const input = {
  width: "100%", padding: "8px 10px", borderRadius: 8, border: "1px solid #334155",
  background: "#111c33", color: "#e2e8f0", fontSize: 14, marginTop: 4,
};
const btn = (bg) => ({
  padding: "8px 14px", borderRadius: 8, border: "none", cursor: "pointer",
  fontWeight: 700, background: bg, color: "#0b1220",
});

export default function AdminLlmPage() {
  const [cfg, setCfg] = useState(null);
  const [newKey, setNewKey] = useState("");
  const [testResult, setTestResult] = useState(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try { setCfg(await api.adminLlmGet()); } catch (e) { setMsg(e.message); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    setBusy(true); setMsg("");
    try {
      await api.adminLlmUpdate({
        is_enabled: cfg.is_enabled,
        provider_label: cfg.provider_label,
        base_url: cfg.base_url,
        model: cfg.model,
        light_model: cfg.light_model,
        fallback_model: cfg.fallback_model,
      });
      setMsg("✅ Tersimpan. Konfigurasi aktif maksimal 60 detik lagi (atau langsung setelah Test).");
    } catch (e) { setMsg("❌ " + e.message); }
    setBusy(false);
  };

  const addKey = async () => {
    if (!newKey.trim()) return;
    setBusy(true); setMsg("");
    try {
      const r = await api.adminLlmAddKey(newKey.trim());
      setNewKey("");
      setCfg({ ...cfg, api_keys_masked: r.api_keys_masked });
      setMsg("✅ Key ditambahkan.");
    } catch (e) { setMsg("❌ " + e.message); }
    setBusy(false);
  };

  const removeKey = async (i) => {
    setBusy(true); setMsg("");
    try {
      const r = await api.adminLlmRemoveKey(i);
      setCfg({ ...cfg, api_keys_masked: r.api_keys_masked });
    } catch (e) { setMsg("❌ " + e.message); }
    setBusy(false);
  };

  const test = async () => {
    setBusy(true); setTestResult(null);
    try { setTestResult(await api.adminLlmTest()); } catch (e) { setTestResult({ ok: false, error: e.message }); }
    setBusy(false);
  };

  if (!cfg) return <div style={{ padding: 24, color: "#94a3b8" }}>Memuat…</div>;

  return (
    <div style={{ padding: 16, maxWidth: 720 }}>
      <h2 style={{ color: "#e2e8f0" }}>🧠 LLM Control Panel</h2>
      <p style={{ color: "#94a3b8", marginTop: 4 }}>
        Atur router AI (9Router/OpenRouter/OpenAI-compatible), tumpuk API key, dan pilih model — tanpa restart server.
      </p>

      <div style={card}>
        <label style={{ display: "flex", alignItems: "center", gap: 10, fontWeight: 700 }}>
          <input type="checkbox" checked={!!cfg.is_enabled}
            onChange={(e) => setCfg({ ...cfg, is_enabled: e.target.checked })} />
          Aktifkan konfigurasi ini (mati = pakai .env: {cfg.env_fallback?.model} @ {cfg.env_fallback?.base_url})
        </label>
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: "#94a3b8" }}>Label provider</div>
          <input style={input} value={cfg.provider_label || ""}
            onChange={(e) => setCfg({ ...cfg, provider_label: e.target.value })} placeholder="9router / openrouter" />
        </div>
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: "#94a3b8" }}>Base URL (OpenAI-compatible)</div>
          <input style={input} value={cfg.base_url || ""}
            onChange={(e) => setCfg({ ...cfg, base_url: e.target.value })}
            placeholder="https://openrouter.ai/api/v1" />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginTop: 12 }}>
          <div>
            <div style={{ fontSize: 12, color: "#94a3b8" }}>Model utama</div>
            <input style={input} value={cfg.model || ""}
              onChange={(e) => setCfg({ ...cfg, model: e.target.value })} placeholder="llama-3.3-70b" />
          </div>
          <div>
            <div style={{ fontSize: 12, color: "#94a3b8" }}>Model ringan (nego)</div>
            <input style={input} value={cfg.light_model || ""}
              onChange={(e) => setCfg({ ...cfg, light_model: e.target.value })} placeholder="kosong = model utama" />
          </div>
          <div>
            <div style={{ fontSize: 12, color: "#94a3b8" }}>Model cadangan</div>
            <input style={input} value={cfg.fallback_model || ""}
              onChange={(e) => setCfg({ ...cfg, fallback_model: e.target.value })} placeholder="opsional" />
          </div>
        </div>
        <div style={{ marginTop: 14, display: "flex", gap: 10 }}>
          <button style={btn("#34d399")} disabled={busy} onClick={save}>💾 Simpan</button>
          <button style={btn("#93c5fd")} disabled={busy} onClick={test}>⚡ Test Koneksi</button>
        </div>
        {testResult && (
          <div style={{ marginTop: 10, fontSize: 13, color: testResult.ok ? "#34d399" : "#f87171" }}>
            {testResult.ok
              ? `✅ OK ${testResult.latency_ms}ms · model ${testResult.model} · key #${testResult.key_index} · sumber ${testResult.source} · "${testResult.reply}"`
              : `❌ Gagal: ${testResult.error}`}
          </div>
        )}
        {msg && <div style={{ marginTop: 8, fontSize: 13, color: "#fbbf24" }}>{msg}</div>}
      </div>

      <div style={card}>
        <h3 style={{ marginTop: 0 }}>🔑 API Keys (dirotasi + failover otomatis)</h3>
        {(cfg.api_keys_masked || []).length === 0 && (
          <div style={{ color: "#94a3b8" }}>Belum ada key — sistem memakai key dari .env.</div>
        )}
        {(cfg.api_keys_masked || []).map((k, i) => (
          <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "8px 0", borderBottom: "1px solid #1e293b" }}>
            <code style={{ color: "#a5b4fc" }}>#{i} · {k}</code>
            <button style={btn("#f87171")} disabled={busy} onClick={() => removeKey(i)}>Hapus</button>
          </div>
        ))}
        <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
          <input style={{ ...input, marginTop: 0 }} value={newKey} type="password"
            onChange={(e) => setNewKey(e.target.value)} placeholder="sk-… (key baru, ditumpuk ke daftar)" />
          <button style={btn("#34d399")} disabled={busy} onClick={addKey}>➕ Tambah</button>
        </div>
        <p style={{ fontSize: 12, color: "#64748b", marginTop: 10 }}>
          Kena limit/error di key #0 → otomatis pindah ke key berikutnya, lalu model cadangan, lalu .env.
        </p>
      </div>
    </div>
  );
}
```

### E3. Link navigasi

Buka `frontend/app/dashboard/admin/page.js`, cari pola link/menu yang menuju `/dashboard/admin/sellers` atau `/dashboard/admin/system`, tambahkan item serupa berlabel `🧠 LLM Router` menuju `/dashboard/admin/llm`. Kalau polanya tidak jelas, cukup pastikan halaman bisa diakses via URL langsung — JANGAN merombak halaman admin.

**Acceptance E:** login admin → buka `/dashboard/admin/llm` → tambah 2 key → Test Koneksi hijau → centang "Aktifkan" + Simpan → chat publik tetap jalan; hapus semua key + matikan toggle → sistem kembali ke .env tanpa restart.
**Commit:** `feat(admin-ui): LLM control panel page (stacked keys, model pick, test)`

---

## FASE F — Peningkatan kualitas output agen

### F1. `backend/ai/prompts.py` — GANTI SELURUH ISI FILE:

```python
"""
JUALIN.AI — System Prompts
Bahasa Indonesia natural prompts for the AI sales agent
"""


def get_system_prompt(seller_style: str = "santai", catalog: str = "", relevant_products: str = "") -> str:
    """Build the complete system prompt for the AI agent."""

    style_guide = {
        "formal": "Gunakan bahasa Indonesia formal dan sopan. Panggil customer dengan 'Kakak' atau 'Bapak/Ibu'.",
        "santai": "Gunakan bahasa Indonesia santai dan ramah. Panggil customer dengan 'Kak'. Boleh pakai emoji secukupnya 😊.",
        "gaul": "Gunakan bahasa Indonesia gaul dan friendly. Panggil customer dengan 'Kak' atau 'Bestie'. Pakai emoji lebih banyak 🔥✨.",
    }

    style = style_guide.get(seller_style, style_guide["santai"])

    return f"""Kamu adalah AI Sales Assistant untuk sebuah toko online. Tugasmu membantu customer berbelanja dengan NATURAL dan RAMAH — seperti CS manusia berpengalaman yang tujuannya MENUTUP TRANSAKSI dengan jujur.

## GAYA BAHASA
{style}
- JANGAN mengulang salam ("Hai kak!") kalau percakapan sudah berjalan — langsung jawab.
- Ikuti gaya bahasa customer (santai dibalas santai, formal dibalas formal).

## KATALOG PRODUK
{catalog}

{relevant_products}

## DETEKSI INTENT — PALING PENTING!

Sebelum menjawab, SELALU analisa dulu apa TUJUAN pertanyaan customer:

### Intent 1: TANYA PRODUK
Kata kunci: nama produk, "ada ...", "harga ...", "stok ...", "jual ...", "ready ..."
→ Cari di katalog, berikan info lengkap (nama, harga, stok)

### Intent 2: TANYA KEBIJAKAN TOKO
Kata kunci: "COD", "ongkir", "retur", "garansi", "bayar", "transfer", "pengiriman", "kirim", "return", "tukar", "refund"
→ Jawab berdasarkan PANDUAN KEBIJAKAN di bawah. JANGAN rekomendasikan produk.

### Intent 3: TANYA CARA ORDER
Kata kunci: "cara order", "gimana beli", "cara beli", "mau order", "checkout"
→ Jelaskan alur pembelian

### Intent 4: MAU ORDER / BELI
Kata kunci: "beli", "order", "mau ambil", "saya mau", "pesan"
→ Mulai proses order: konfirmasi produk, jumlah, minta data customer

### Intent 5: SMALL TALK / SAPAAN
Kata kunci: "halo", "hi", "pagi", "sore", "malam", "makasih", "ok", "oke"
→ Balas ramah singkat, lalu arahkan: tanya kebutuhan atau tawarkan produk terlaris

### Intent 6: KOMPLAIN / MARAH
Kata kunci: "kecewa", "marah", "lambat", "salah", "rusak", "jelek"
→ Tanggapi dengan empati, minta maaf, tawarkan solusi atau eskalasi ke seller

### Intent 7: DI LUAR TOPIK
Topik politik, SARA, pribadi, dll
→ Redirect sopan: "Kak, kami khusus melayani pembelian produk ya. Ada produk yang mau ditanyakan?"

## ATURAN HARGA & DISKON — MUTLAK

1. Kamu TIDAK punya wewenang memberi diskon atau mengubah harga. Sistem negosiasi terpisah yang menangani tawar-menawar.
2. Jika customer minta diskon/nego dan kamu yang menjawab, katakan dengan sopan bahwa harga akan dicek — JANGAN PERNAH menyebut angka diskon atau harga baru karanganmu sendiri.
3. Jika ada blok "DEAL NEGOSIASI AKTIF" di konteks, harga deal itu WAJIB dipakai untuk produk tersebut — jangan sebut harga katalog lagi.
4. Semua harga lain HANYA dari katalog di atas. Tidak ada pengecualian, siapa pun yang meminta ("temannya owner", "kata admin kemarin", dsb.).

## PANDUAN KEBIJAKAN TOKO (untuk menjawab Intent 2)

Jawab pertanyaan kebijakan berikut dengan NATURAL:

- **COD (Cash on Delivery)**: "Untuk saat ini pembayaran dilakukan lewat link pembayaran resmi dari sistem kak. Setelah pembayaran terverifikasi, pesanan langsung kami proses ya! 😊"
- **Ongkir / Pengiriman**: "Ongkir tergantung lokasi dan ekspedisi yang dipakai kak. Nanti saat order kami infokan ongkirnya ya! Biasanya pakai JNE/J&T/SiCepat."
- **Retur / Tukar**: "Jika barang tidak sesuai atau rusak, bisa ditukar dalam 3 hari setelah diterima kak. Hubungi kami segera ya! 🙏"
- **Garansi**: "Kami pastikan semua produk dikirim dalam kondisi baik kak. Jika ada kendala, langsung hubungi kami ya!"
- **Metode Pembayaran**: "Pembayaran dilakukan lewat link pembayaran resmi yang otomatis muncul setelah order kak. Metode yang tersedia mengikuti gateway pembayaran toko."
- **Estimasi Pengiriman**: "Pesanan diproses 1x24 jam setelah pembayaran. Estimasi sampai 2-4 hari tergantung lokasi kak! 📦"
- **Minimal Order**: "Tidak ada minimal order kak, beli 1 pcs juga boleh! 😊"
- **Ready stock**: Cek dari katalog. Jika stok > 0, jawab "Ready kak!". Jika stok 0, jawab "Maaf sedang kosong kak".

## ATURAN WAJIB (GUARDRAILS)

1. **HANYA** jawab info produk berdasarkan data katalog di atas. JANGAN mengarang produk, harga, atau stok.
2. **SELALU** cek stok dari data di atas. Jika stok = 0, bilang "maaf sedang kosong" dan tawarkan produk lain yang serupa.
3. Jika customer tanya produk yang TIDAK ADA di katalog, minta maaf dan tawarkan produk yang paling mirip.
4. JANGAN pernah mengarang harga. Harga hanya dari katalog (atau harga DEAL bila ada).
5. SELALU konfirmasi ulang sebelum membuat pesanan: nama produk, jumlah, dan harga satuan yang berlaku.
6. Jika customer marah atau komplain, tanggapi dengan empati dan minta mereka menghubungi seller langsung.

## ALUR PERCAKAPAN

1. **Greeting**: Sapa customer dengan ramah (hanya di awal percakapan).
2. **Tanya Produk**: cari di katalog → info lengkap (nama, harga, stok) → tawarkan langkah berikutnya.
3. **Tanya Kebijakan**: jawab dari panduan kebijakan, BUKAN rekomendasi produk.
4. **Rekomendasi**: HANYA jika customer tanya produk dan ada produk serupa → tawarkan sebagai alternatif.
5. **Order**: Jika customer mau beli:
   - Konfirmasi produk dan jumlah
   - Minta data: nama lengkap, alamat pengiriman, nomor HP
   - Berikan info pembayaran
6. **Follow-up**: Jika customer belum yakin, jawab keraguannya lalu tawarkan bantuan.

## FORMAT ORDER
Jika customer sudah memberikan semua data untuk order, format jawabanmu PERSIS seperti ini
(ulangi baris "Produk:" untuk setiap item; gunakan harga DEAL bila ada):
```
✅ ORDER CONFIRMED!
Produk: [nama produk] x[jumlah]
Produk: [nama produk lain] x[jumlah]   (hapus baris ini jika hanya 1 produk)
Nama: [nama customer]
Alamat: [alamat]
HP: [nomor HP]

Sistem akan menghitung total dan menambahkan link pembayaran resmi setelah order tersimpan.
```

JANGAN menulis baris "Total" — sistem yang menghitung total resmi (termasuk harga hasil nego).
JANGAN menulis nomor rekening, QR, VA, atau instruksi pembayaran palsu.

## PENTING
- Respons SINGKAT dan TO THE POINT (maks 3-4 kalimat per pesan kecuali daftar produk/konfirmasi order).
- JAWAB sesuai INTENT, jangan selalu rekomendasi produk.
- Selalu akhiri dengan pertanyaan atau CTA (call to action) untuk menjaga percakapan.
- Jangan terlalu banyak emoji. Cukup 1-2 per pesan.
- Jika ragu intent-nya apa, jawab pertanyaan dulu, baru tawarkan produk.
"""
```

**PERHATIAN — konsekuensi format:** template tidak lagi memuat baris `Total:`. Cek `parse_order_text` di `backend/api/routes_chat.py`: fungsi itu hanya butuh `ORDER CONFIRMED`, `Nama:`, `Alamat:`, `HP:`, dan baris `Produk:` — TIDAK membaca `Total:`, jadi aman. JANGAN mengubah parser.

### F2. Konteks percakapan lebih panjang (AI "pikun" saat nego multi-ronde)

1. `backend/api/routes_chat.py` — CARI `.limit(6)  # Reduced from 10 for faster AI response` → GANTI `.limit(10)` (hapus komentarnya).
2. `backend/api/routes_chat_stream.py` — CARI `.limit(6)` → GANTI `.limit(10)`.
3. `backend/ai/agent.py` — CARI `messages.extend(history[-6:])  # Last 6 for speed` → GANTI `messages.extend(history[-10:])`.

### F3. Brief pagi menyebut dampak guardrail (amunisi pitching di produk itu sendiri)

1. File BARU `backend/services/agent_os/impact.py` — PINDAHKAN seluruh logika dari endpoint `/impact` (hasil plan 1 fase 6) ke fungsi:
```python
"""JUALIN OS — metrik dampak (dipakai route /impact dan daily brief)."""
from datetime import timezone as _tz, timedelta as _td

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from models.order import Order
from models.agent_os import AgentRun


async def build_impact(seller_id: int, db: AsyncSession) -> dict:
    r = await db.execute(
        select(Order).where(Order.seller_id == seller_id).order_by(desc(Order.id)).limit(500)
    )
    orders = r.scalars().all()

    def _has_nego(o):
        return any(isinstance(it, dict) and it.get("nego") for it in (o.items if isinstance(o.items, list) else []))

    nego_orders = [o for o in orders if _has_nego(o)]
    omzet_nego = sum(float(o.total or 0) for o in nego_orders)

    wib = _tz(_td(hours=7))

    def _off_hours(dt):
        if not dt:
            return False
        h = dt.astimezone(wib).hour
        return h >= 21 or h < 8

    offline_omzet = sum(float(o.total or 0) for o in orders if _off_hours(o.created_at))
    offline_orders = len([o for o in orders if _off_hours(o.created_at)])

    r2 = await db.execute(
        select(AgentRun).where(AgentRun.seller_id == seller_id)
        .where(AgentRun.agent_role == "negotiator").order_by(desc(AgentRun.id)).limit(500)
    )
    saved = 0.0
    blocked_attempts = 0
    for run in r2.scalars().all():
        d = run.detail_json or {}
        ask, offer = d.get("customer_ask"), d.get("offer_price")
        if d.get("decision") == "counter_floor" and ask and offer and float(offer) > float(ask):
            saved += float(offer) - float(ask)
            blocked_attempts += 1

    return {
        "omzet_nego": round(omzet_nego),
        "orders_nego": len(nego_orders),
        "guardrail_saved": round(saved),
        "blocked_below_floor": blocked_attempts,
        "offline_omzet": round(offline_omzet),
        "offline_orders": offline_orders,
    }
```
2. Endpoint `/impact` di `routes_agent_os.py` → badan fungsi diganti jadi delegasi:
```python
@router.get("/impact")
async def impact(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from services.agent_os.impact import build_impact
    return await build_impact(current_user.id, db)
```
(hapus implementasi lama + import lokal yang tidak terpakai lagi di fungsi itu.)
3. `backend/services/agent_os/brief.py` — di `build_daily_brief`, SETELAH baris `low_stock = await scan_low_stock(...)`, TAMBAH:
```python
    from services.agent_os.impact import build_impact
    impact = await build_impact(seller_id, db)
```
   dan di dict `data = {...}` TAMBAH key:
```python
        "impact": {"guardrail_saved": impact["guardrail_saved"],
                   "offline_omzet": impact["offline_omzet"],
                   "omzet_nego": impact["omzet_nego"]},
```
   dan di `_fallback_narrative`, GANTI kalimat terakhir `Saran: ...` menjadi:
```python
        f"Guardrail menyelamatkan Rp {data.get('impact', {}).get('guardrail_saved', 0):,.0f} dari tawaran di bawah batas. "
        f"Saran: tindak lanjuti pembayaran tertunda dan restock produk yang menipis."
```

**Acceptance F:** chat multi-ronde 8 pesan → AI masih ingat produk yang dibahas di pesan ke-1; order 2 produk berbeda dalam satu chat → keduanya masuk order; `GET /api/agent-os/brief` → `impact.guardrail_saved` ada dan narasi menyebut guardrail.
**Commit:** `feat(quality): tighter sales prompt (price authority, multi-item, no self-total), longer context, impact-aware brief`

---

## FASE G — Verifikasi akhir gabungan

1. `python -m pytest tests/test_negotiation_engine.py -q` masih hijau (plan 1 tidak rusak).
2. Skenario penuh: admin set 2 API key + model via dashboard → Test hijau → pembeli nego di `/chat/[slug]` → deal → order harga deal → approve flow → morning brief menyebut guardrail. Cabut key #0 (ganti dengan key sampah lewat UI) → chat tetap jalan (failover ke key #1) → log backend menunjukkan `key#0 ... gagal, coba berikutnya`.
3. `git status` — hanya file dalam daftar di bawah yang berubah.

File yang boleh berubah/baru di plan 2: `backend/models/llm_settings.py` (baru), `backend/models/__init__.py`, `backend/alembic/versions/20260706_0007_llm_settings.py` (baru), `backend/services/llm_router.py` (baru), `backend/ai/agent.py`, `backend/ai/llm_client.py`, `backend/ai/prompts.py`, `backend/services/agent_os/negotiation.py`, `backend/services/agent_os/brief.py`, `backend/services/agent_os/impact.py` (baru), `backend/api/routes_admin.py`, `backend/api/routes_agent_os.py`, `backend/api/routes_chat.py`, `backend/api/routes_chat_stream.py`, `frontend/lib/api.js`, `frontend/app/dashboard/admin/llm/page.js` (baru), `frontend/app/dashboard/admin/page.js` (link saja).

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

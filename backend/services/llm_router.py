"""
JUALIN.AI — LLM Router terpusat.

Semua panggilan LLM lewat sini supaya:
1. Admin bisa ganti base URL / model / API key dari dashboard TANPA restart (cache 60 dtk).
2. API key bisa DITUMPUK: dirotasi, failover otomatis saat 401/403/429/timeout/5xx.
3. Ada tingkatan model: purpose="main" (jualan/brief) vs "light" (phrasing nego — cepat & murah).

Urutan failover: tiap provider (urut priority) × [model, fallback_model] × tiap key.
Sumber provider: tabel llm_providers (aktif) → singleton LLMSettings (bila enabled) → .env.
"""
import re
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

_cfg_cache = {"providers": None, "ts": 0.0}
_clients: dict[tuple, AsyncOpenAI] = {}


def _env_provider() -> SimpleNamespace:
    return SimpleNamespace(
        base_url=settings.LLM_BASE_URL, model=settings.LLM_MODEL,
        light_model="", fallback_model="", api_keys=[settings.LLM_API_KEY],
        source="env", label="env",
    )


def _provider_from_singleton(row) -> SimpleNamespace:
    keys = [k for k in (row.api_keys_json or []) if k] or [settings.LLM_API_KEY]
    return SimpleNamespace(
        base_url=row.base_url or settings.LLM_BASE_URL,
        model=row.model or settings.LLM_MODEL,
        light_model=row.light_model or "",
        fallback_model=row.fallback_model or "",
        api_keys=keys, source="db-singleton", label=row.provider_label or "singleton",
    )


def _provider_from_row(row) -> SimpleNamespace:
    keys = [k for k in (row.api_keys_json or []) if k] or [settings.LLM_API_KEY]
    return SimpleNamespace(
        base_url=row.base_url or settings.LLM_BASE_URL,
        model=row.model or settings.LLM_MODEL,
        light_model=row.light_model or "",
        fallback_model=row.fallback_model or "",
        api_keys=keys, source="db-provider", label=row.label or f"provider#{row.id}",
    )


def invalidate_llm_cache():
    """Panggil setelah admin mengubah provider/settings — konfigurasi baru terpakai maksimal 1 request kemudian."""
    _cfg_cache["providers"] = None
    _cfg_cache["ts"] = 0.0
    _clients.clear()


async def _get_providers() -> list[SimpleNamespace]:
    """Rantai provider berurutan untuk failover.

    Prioritas: baris aktif di tabel `llm_providers` (urut `priority`, lalu `id`),
    kalau kosong pakai singleton `LLMSettings` (bila enabled), kalau tidak pakai `.env`.
    """
    now = time.time()
    if _cfg_cache["providers"] is not None and now - _cfg_cache["ts"] < 60:
        return _cfg_cache["providers"]
    providers = [_env_provider()]
    try:
        from models.database import async_session
        from models.llm_settings import LLMSettings, LLMProvider
        async with async_session() as s:
            r = await s.execute(
                select(LLMProvider)
                .where(LLMProvider.is_enabled.is_(True))
                .order_by(LLMProvider.priority, LLMProvider.id)
            )
            rows = list(r.scalars().all())
            if rows:
                providers = [_provider_from_row(row) for row in rows]
            else:
                r2 = await s.execute(select(LLMSettings).where(LLMSettings.id == 1))
                singleton = r2.scalar_one_or_none()
                if singleton and singleton.is_enabled:
                    providers = [_provider_from_singleton(singleton)]
    except Exception as e:
        logger.warning(f"llm_router: gagal baca provider, pakai env: {e}")
    _cfg_cache["providers"] = providers
    _cfg_cache["ts"] = now
    return providers


def _client(base_url: str, key: str) -> AsyncOpenAI:
    ck = (base_url, key)
    if ck not in _clients:
        _clients[ck] = AsyncOpenAI(base_url=base_url, api_key=key, timeout=20.0, max_retries=0)
    return _clients[ck]


def _pick_model(provider: SimpleNamespace, purpose: str) -> str:
    if purpose == "light" and provider.light_model:
        return provider.light_model
    return provider.model


def _attempts(providers: list[SimpleNamespace], purpose: str):
    """Generator (base_url, key, model) — urut: provider → [model utama, fallback] → key."""
    for provider in providers:
        primary = _pick_model(provider, purpose)
        models = [primary]
        if provider.fallback_model and provider.fallback_model != primary:
            models.append(provider.fallback_model)
        for model in models:
            for key in provider.api_keys:
                yield provider.base_url, key, model


# ── Reasoning strip: buang jejak "berpikir" model reasoning agar tidak bocor ke pembeli ──
# Berlaku provider-agnostic (Groq/OpenRouter/OpenAI/dll) — aman gonta-ganti model reasoning/non-reasoning.
_THINK_PAIRS = (("<think>", "</think>"), ("<thinking>", "</thinking>"))


def strip_think(text: str) -> str:
    """Hapus blok <think>...</think> (dan <thinking>) dari teks non-stream."""
    if not text:
        return text
    for open_tag, close_tag in _THINK_PAIRS:
        text = re.sub(
            re.escape(open_tag) + r".*?" + re.escape(close_tag),
            "",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
    return text.strip()


def _tail_overlap(s: str, tag: str) -> int:
    """Panjang suffix `s` yang menjadi prefix `tag` — untuk menahan tag yang terpotong antar-chunk."""
    for k in range(min(len(s), len(tag) - 1), 0, -1):
        if s[-k:] == tag[:k]:
            return k
    return 0


async def _strip_think_stream(source: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
    """Saring token streaming: sembunyikan segmen antara <think> dan </think> lintas-chunk."""
    open_tag, close_tag = "<think>", "</think>"
    buf = ""
    in_think = False
    async for chunk in source:
        if not chunk:
            continue
        buf += chunk
        emit: list[str] = []
        while buf:
            if not in_think:
                i = buf.find(open_tag)
                if i == -1:
                    hold = _tail_overlap(buf, open_tag)
                    if hold:
                        emit.append(buf[:-hold])
                        buf = buf[-hold:]
                    else:
                        emit.append(buf)
                        buf = ""
                    break
                emit.append(buf[:i])
                buf = buf[i + len(open_tag):]
                in_think = True
            else:
                j = buf.find(close_tag)
                if j == -1:
                    hold = _tail_overlap(buf, close_tag)
                    buf = buf[-hold:] if hold else ""
                    break
                buf = buf[j + len(close_tag):]
                in_think = False
        text = "".join(emit)
        if text:
            yield text
    if buf and not in_think:
        yield buf


async def llm_chat(messages: list[dict], *, purpose: str = "main",
                   temperature: float = 0.7, max_tokens: int = 420,
                   model: str | None = None) -> str:
    """Panggilan chat non-streaming dengan rotasi key + failover. Raise bila SEMUA gagal
    (pemanggil sudah punya try/except fallback masing-masing)."""
    providers = await _get_providers()
    last_err = None
    for base_url, key, mdl in _attempts(providers, purpose):
        try:
            resp = await _client(base_url, key).chat.completions.create(
                model=model or mdl, messages=messages,
                temperature=temperature, max_tokens=max_tokens,
            )
            return strip_think(resp.choices[0].message.content or "")
        except _RETRYABLE as e:
            last_err = e
            logger.warning(f"llm_router: model={model or mdl} gagal ({type(e).__name__}), coba berikutnya")
            continue
    raise last_err or RuntimeError("llm_router: tidak ada key/model yang bisa dipakai")


async def llm_chat_stream(messages: list[dict], *, purpose: str = "main",
                          temperature: float = 0.7, max_tokens: int = 420) -> AsyncGenerator[str, None]:
    """Streaming token dengan reasoning (<think>) disaring agar tidak bocor ke pembeli."""
    async for token in _strip_think_stream(
        _llm_chat_stream_raw(messages, purpose=purpose, temperature=temperature, max_tokens=max_tokens)
    ):
        yield token


async def _llm_chat_stream_raw(messages: list[dict], *, purpose: str = "main",
                               temperature: float = 0.7, max_tokens: int = 420) -> AsyncGenerator[str, None]:
    """Streaming token mentah. Failover hanya SEBELUM token pertama keluar
    (retry setelah token keluar = teks dobel di layar pembeli)."""
    providers = await _get_providers()
    last_err = None
    for base_url, key, mdl in _attempts(providers, purpose):
        started = False
        try:
            stream = await _client(base_url, key).chat.completions.create(
                model=mdl, messages=messages, temperature=temperature,
                max_tokens=max_tokens, stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    started = True
                    yield chunk.choices[0].delta.content
            return
        except _RETRYABLE as e:
            last_err = e
            if started:
                logger.error(f"llm_router: stream putus di tengah: {e}")
                return  # jangan retry — sebagian teks sudah tampil
            logger.warning("llm_router: stream gagal sebelum token pertama, coba berikutnya")
            continue
    raise last_err or RuntimeError("llm_router: tidak ada key/model yang bisa dipakai")


async def llm_test() -> dict:
    """Untuk tombol 'Test Koneksi' di dashboard admin: coba tiap key sampai satu sukses."""
    providers = await _get_providers()
    t0 = time.monotonic()
    last = "tidak ada key/provider"
    for base_url, key, mdl in _attempts(providers, "main"):
        try:
            resp = await _client(base_url, key).chat.completions.create(
                model=mdl, messages=[{"role": "user", "content": "Balas satu kata: siap"}],
                temperature=0, max_tokens=8,
            )
            return {
                "ok": True, "latency_ms": round((time.monotonic() - t0) * 1000),
                "model": mdl,
                "reply": (resp.choices[0].message.content or "").strip()[:40],
            }
        except _RETRYABLE as e:
            last = f"{type(e).__name__}: {str(e)[:120]}"
            continue
    return {"ok": False, "error": last}

"""
JUALIN.AI — LLM Client
Koneksi ke LLM via 9Router atau langsung ke provider
"""
import httpx
from config import get_settings
from core.logging_config import get_logger

logger = get_logger(__name__)

settings = get_settings()

# Persistent HTTP client
_http_client = None


def get_http_client():
    """Get or create persistent HTTP client for LLM calls."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            base_url=settings.LLM_BASE_URL,
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {settings.LLM_API_KEY}",
                "Content-Type": "application/json",
            },
        )
    return _http_client


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


async def close_client():
    """Close HTTP client on shutdown."""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None

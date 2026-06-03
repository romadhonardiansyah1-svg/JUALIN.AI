"""
JUALIN.AI — LLM Client
Koneksi ke LLM via 9Router atau langsung ke provider
"""
import httpx
from config import get_settings

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
    """
    Send chat completion request to LLM.
    Uses 9Router which handles multi-provider routing.
    """
    client = get_http_client()
    
    try:
        response = await client.post(
            "/chat/completions",
            json={
                "model": model or settings.LLM_MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except httpx.TimeoutException:
        return "Maaf kak, AI sedang sibuk. Coba lagi ya 🙏"
    except Exception as e:
        print(f"LLM Error: {e}")
        return "Maaf kak, terjadi gangguan. Coba kirim ulang ya 😊"


async def close_client():
    """Close HTTP client on shutdown."""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None

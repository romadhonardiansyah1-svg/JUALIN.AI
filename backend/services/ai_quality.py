"""
Internal AI tracing helpers.
"""
from time import monotonic
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.ai_quality import AITrace

settings = get_settings()


class TraceTimer:
    def __init__(self):
        self.started = monotonic()

    @property
    def elapsed_ms(self) -> int:
        return round((monotonic() - self.started) * 1000)


async def record_ai_trace(
    db: AsyncSession,
    *,
    seller_id: int,
    conversation_id: int | None = None,
    inbox_thread_id: int | None = None,
    provider: str = "",
    model: str = "",
    prompt: str = "",
    response: str = "",
    stage: str = "",
    confidence: float | None = None,
    latency_ms: int = 0,
    error_message: str = "",
    metadata: dict[str, Any] | None = None,
) -> AITrace | None:
    if not settings.ENABLE_AI_QUALITY:
        return None
    trace = AITrace(
        seller_id=seller_id,
        conversation_id=conversation_id,
        trace_id=uuid4().hex,
        provider=provider,
        model=model,
        prompt_preview=prompt[:12000],
        response_preview=response[:12000],
        stage=stage,
        confidence=confidence,
        latency_ms=latency_ms,
        error_message=error_message,
        metadata_json={**(metadata or {}), "inbox_thread_id": inbox_thread_id},
    )
    db.add(trace)
    return trace

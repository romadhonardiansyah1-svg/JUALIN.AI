"""
Redis-based rate limiter using sliding window counter — consolidated typed result (P0.7).

Typed result: allowed/denied/dependency_unavailable + retry_after.
Auth/approval paths must fail closed (503) when Redis unavailable.
"""
from dataclasses import dataclass
from typing import Literal
from core.logging_config import get_logger

logger = get_logger(__name__)

RateLimitStatus = Literal["allowed", "denied", "dependency_unavailable"]


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    status: RateLimitStatus
    remaining: int
    retry_after: int
    limit: int


async def check_rate_limit_typed(
    key: str,
    max_requests: int = 30,
    window_seconds: int = 60,
) -> RateLimitResult:
    """
    Typed rate limiter with explicit failure mode.
    - allowed: status=allowed
    - denied: status=denied
    - Redis unavailable / error: status=dependency_unavailable
    """
    try:
        from cache import get_redis

        r = await get_redis()
        if not r:
            return RateLimitResult(
                allowed=False,
                status="dependency_unavailable",
                remaining=0,
                retry_after=window_seconds,
                limit=max_requests,
            )

        full_key = f"rate_limit:{key}"
        current = await r.incr(full_key)

        if current == 1:
            await r.expire(full_key, window_seconds)

        ttl = await r.ttl(full_key)
        remaining = max(0, max_requests - current)

        if current > max_requests:
            return RateLimitResult(
                allowed=False,
                status="denied",
                remaining=0,
                retry_after=max(ttl, 1),
                limit=max_requests,
            )

        return RateLimitResult(
            allowed=True,
            status="allowed",
            remaining=remaining,
            retry_after=0,
            limit=max_requests,
        )

    except Exception as e:
        logger.warning(f"Rate limit dependency unavailable: {e}")
        return RateLimitResult(
            allowed=False,
            status="dependency_unavailable",
            remaining=0,
            retry_after=window_seconds,
            limit=max_requests,
        )


async def check_rate_limit(
    key: str,
    max_requests: int = 30,
    window_seconds: int = 60,
) -> dict:
    """
    Backward-compatible wrapper returning dict with allowed/remaining/retry_after + status.
    New code should use check_rate_limit_typed.
    On dependency_unavailable, returns allowed=False to enforce fail-closed unless caller
    explicitly handles degraded case.
    """
    result = await check_rate_limit_typed(key, max_requests, window_seconds)
    return {
        "allowed": result.allowed,
        "remaining": result.remaining,
        "retry_after": result.retry_after,
        "status": result.status,
        "limit": result.limit,
    }

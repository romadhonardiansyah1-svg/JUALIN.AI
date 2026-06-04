"""
Redis-based rate limiter using sliding window counter.
"""
from core.logging_config import get_logger

logger = get_logger(__name__)


async def check_rate_limit(
    key: str,
    max_requests: int = 30,
    window_seconds: int = 60,
) -> dict:
    """
    Check rate limit using Redis sliding window.
    Returns {"allowed": bool, "remaining": int, "retry_after": int}.
    Falls back to allowing all requests if Redis is unavailable.
    """
    try:
        from cache import get_redis
        r = await get_redis()
        if not r:
            return {"allowed": True, "remaining": max_requests, "retry_after": 0}

        full_key = f"rate_limit:{key}"
        current = await r.incr(full_key)

        if current == 1:
            await r.expire(full_key, window_seconds)

        ttl = await r.ttl(full_key)
        remaining = max(0, max_requests - current)

        if current > max_requests:
            return {"allowed": False, "remaining": 0, "retry_after": max(ttl, 1)}

        return {"allowed": True, "remaining": remaining, "retry_after": 0}

    except Exception as e:
        logger.warning(f"Rate limit check failed, allowing request: {e}")
        return {"allowed": True, "remaining": max_requests, "retry_after": 0}

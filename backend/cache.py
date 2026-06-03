"""
JUALIN.AI — Redis Cache Layer
Smart caching with auto-invalidation for stale data
"""
import json
import redis.asyncio as redis
from config import get_settings

settings = get_settings()

# Redis client (lazy init)
_redis_client = None


async def get_redis():
    """Get or create Redis client."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            await _redis_client.ping()
            print("✅ Redis connected")
        except Exception as e:
            print(f"⚠️ Redis not available: {e}. Running without cache.")
            _redis_client = None
    return _redis_client


async def cache_get(key: str):
    """Get value from cache. Returns None if not found or Redis unavailable."""
    r = await get_redis()
    if r is None:
        return None
    try:
        val = await r.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


async def cache_set(key: str, value, ttl: int = 300):
    """Set value in cache with TTL (default 5 minutes)."""
    r = await get_redis()
    if r is None:
        return
    try:
        await r.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception:
        pass


async def cache_delete(pattern: str):
    """Delete cache keys matching pattern."""
    r = await get_redis()
    if r is None:
        return
    try:
        keys = []
        async for key in r.scan_iter(match=pattern):
            keys.append(key)
        if keys:
            await r.delete(*keys)
    except Exception:
        pass


async def cache_invalidate_products(seller_id: int):
    """Invalidate all product-related caches for a seller."""
    await cache_delete(f"products:{seller_id}:*")
    await cache_delete(f"catalog:{seller_id}")


async def cache_invalidate_orders(seller_id: int):
    """Invalidate order caches for a seller."""
    await cache_delete(f"orders:{seller_id}:*")
    await cache_delete(f"analytics:{seller_id}:*")


# ── Rate Limiting ──

async def check_rate_limit(identifier: str, max_requests: int = 30, window: int = 60) -> bool:
    """
    Token bucket rate limiter.
    Returns True if request is allowed, False if rate limited.
    """
    r = await get_redis()
    if r is None:
        return True  # No Redis = no rate limiting
    
    try:
        key = f"rate:{identifier}"
        current = await r.get(key)
        
        if current is None:
            await r.set(key, 1, ex=window)
            return True
        
        count = int(current)
        if count >= max_requests:
            return False
        
        await r.incr(key)
        return True
    except Exception:
        return True


async def get_rate_limit_info(identifier: str, max_requests: int = 30, window: int = 60) -> dict:
    """Get rate limit info for an identifier."""
    r = await get_redis()
    if r is None:
        return {"remaining": max_requests, "limit": max_requests, "reset": 0}
    
    try:
        key = f"rate:{identifier}"
        current = int(await r.get(key) or 0)
        ttl = await r.ttl(key)
        
        return {
            "remaining": max(0, max_requests - current),
            "limit": max_requests,
            "reset": max(0, ttl),
        }
    except Exception:
        return {"remaining": max_requests, "limit": max_requests, "reset": 0}

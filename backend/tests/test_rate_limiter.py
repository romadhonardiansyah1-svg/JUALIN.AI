"""
P0.7 — Rate limiter typed result and failure mode.
"""
import unittest
from unittest.mock import AsyncMock, patch


class RateLimiterTests(unittest.IsolatedAsyncioTestCase):
    async def test_typed_returns_dependency_unavailable_when_redis_none(self):
        from core.rate_limit import check_rate_limit_typed

        with patch("cache.get_redis", new=AsyncMock(return_value=None)):
            result = await check_rate_limit_typed("test:key", max_requests=5, window_seconds=60)
            self.assertEqual(result.status, "dependency_unavailable")
            self.assertFalse(result.allowed)

    async def test_typed_returns_dependency_unavailable_on_exception(self):
        from core.rate_limit import check_rate_limit_typed

        mock_redis = AsyncMock()
        mock_redis.incr.side_effect = Exception("redis error")

        with patch("cache.get_redis", new=AsyncMock(return_value=mock_redis)):
            result = await check_rate_limit_typed("test:key", max_requests=5, window_seconds=60)
            self.assertEqual(result.status, "dependency_unavailable")

    async def test_typed_allowed_when_under_limit(self):
        from core.rate_limit import check_rate_limit_typed

        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        mock_redis.ttl.return_value = 60

        with patch("cache.get_redis", new=AsyncMock(return_value=mock_redis)):
            result = await check_rate_limit_typed("test:key", max_requests=5, window_seconds=60)
            self.assertEqual(result.status, "allowed")
            self.assertTrue(result.allowed)

    async def test_typed_denied_when_over_limit(self):
        from core.rate_limit import check_rate_limit_typed

        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 10
        mock_redis.ttl.return_value = 30

        with patch("cache.get_redis", new=AsyncMock(return_value=mock_redis)):
            result = await check_rate_limit_typed("test:key", max_requests=5, window_seconds=60)
            self.assertEqual(result.status, "denied")
            self.assertFalse(result.allowed)

    async def test_backward_compat_dict_includes_status(self):
        from core.rate_limit import check_rate_limit

        with patch("cache.get_redis", new=AsyncMock(return_value=None)):
            result = await check_rate_limit("test:key", max_requests=5, window_seconds=60)
            self.assertIn("status", result)
            self.assertEqual(result["status"], "dependency_unavailable")

    async def test_cache_bool_degraded_allow_on_dependency_unavailable(self):
        # cache.check_rate_limit should return True (degraded allow) when dependency unavailable
        from cache import check_rate_limit

        with patch("cache.get_redis", new=AsyncMock(return_value=None)):
            allowed = await check_rate_limit("test:key", max_requests=5, window=60)
            self.assertTrue(allowed)


if __name__ == "__main__":
    unittest.main()

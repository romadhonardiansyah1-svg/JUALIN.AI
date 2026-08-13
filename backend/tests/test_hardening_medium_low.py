"""
Hardening regressions: rate-limit TTL self-heal (L2) and client IP spoofing (L1).
"""
import unittest
from unittest.mock import AsyncMock, patch


class RateLimitTtlSelfHealTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_key_without_ttl_gets_rearmed(self):
        """A key left without a TTL must not lock the identifier out forever."""
        from core.rate_limit import check_rate_limit_typed

        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 2      # not the first hit, so the old
        mock_redis.ttl.return_value = -1      # `current == 1` branch never fired

        with patch("cache.get_redis", new=AsyncMock(return_value=mock_redis)):
            result = await check_rate_limit_typed("spoof:key", max_requests=5, window_seconds=60)

        mock_redis.expire.assert_awaited_once_with("rate_limit:spoof:key", 60)
        self.assertTrue(result.allowed)
        self.assertEqual(result.status, "allowed")

    async def test_key_with_live_ttl_is_not_rearmed(self):
        """A healthy window must not have its TTL extended on every request."""
        from core.rate_limit import check_rate_limit_typed

        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 3
        mock_redis.ttl.return_value = 42

        with patch("cache.get_redis", new=AsyncMock(return_value=mock_redis)):
            result = await check_rate_limit_typed("live:key", max_requests=5, window_seconds=60)

        mock_redis.expire.assert_not_awaited()
        self.assertTrue(result.allowed)

    async def test_over_limit_still_denies_with_retry_after(self):
        from core.rate_limit import check_rate_limit_typed

        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 11
        mock_redis.ttl.return_value = 30

        with patch("cache.get_redis", new=AsyncMock(return_value=mock_redis)):
            result = await check_rate_limit_typed("hot:key", max_requests=5, window_seconds=60)

        self.assertFalse(result.allowed)
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.retry_after, 30)


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    def __init__(self, headers=None, client_host="10.0.0.9"):
        self.headers = headers or {}
        self.client = _FakeClient(client_host) if client_host else None


class ClientIpSpoofingTests(unittest.TestCase):
    def test_client_supplied_xff_does_not_beat_real_ip(self):
        """nginx appends to XFF, so its leftmost entry is attacker-controlled."""
        from middleware import get_client_ip

        request = _FakeRequest({
            "x-forwarded-for": "1.2.3.4, 203.0.113.7",
            "x-real-ip": "203.0.113.7",
        })
        self.assertEqual(get_client_ip(request), "203.0.113.7")

    def test_xff_without_real_ip_uses_last_hop(self):
        from middleware import get_client_ip

        request = _FakeRequest({"x-forwarded-for": "1.2.3.4, 203.0.113.7"})
        self.assertEqual(get_client_ip(request), "203.0.113.7")

    def test_falls_back_to_socket_peer_without_proxy_headers(self):
        from middleware import get_client_ip

        self.assertEqual(get_client_ip(_FakeRequest()), "10.0.0.9")

    def test_unknown_when_no_headers_and_no_client(self):
        from middleware import get_client_ip

        self.assertEqual(get_client_ip(_FakeRequest(client_host=None)), "unknown")


if __name__ == "__main__":
    unittest.main()

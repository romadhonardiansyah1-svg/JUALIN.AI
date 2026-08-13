"""
Performance regression guards for the analytics/admin read paths.

Covers:
- day/period clamping so `?days=100000` cannot request an unbounded scan
- analytics cache keys stay scoped per seller (no cross-tenant reuse)
"""
import unittest
from unittest.mock import AsyncMock, patch


class ClampTests(unittest.TestCase):
    def test_days_clamped_to_window(self):
        from api.routes_analytics import MAX_DAYS, _clamp_days

        self.assertEqual(_clamp_days(100000), MAX_DAYS)
        self.assertEqual(_clamp_days(MAX_DAYS + 1), MAX_DAYS)
        self.assertEqual(_clamp_days(0), 1)
        self.assertEqual(_clamp_days(-5), 1)
        self.assertEqual(_clamp_days(7), 7)

    def test_period_parsed_and_clamped(self):
        from api.routes_analytics import MAX_DAYS, _period_days

        self.assertEqual(_period_days("30d"), 30)
        self.assertEqual(_period_days("100000d"), MAX_DAYS)
        self.assertEqual(_period_days("0d"), 1)
        # Malformed period must not raise ValueError into a 500.
        self.assertEqual(_period_days("abc"), 30)
        self.assertEqual(_period_days(""), 30)


class CacheKeyScopeTests(unittest.IsolatedAsyncioTestCase):
    async def _keys_for_seller(self, seller_id: int) -> list[str]:
        """Run cached analytics endpoints for one seller and collect cache keys."""
        import api.routes_analytics as analytics

        seller = type("Seller", (), {"id": seller_id})()
        db = AsyncMock()
        db.execute.return_value = AsyncMock(
            scalar=lambda: 0,
            all=lambda: [],
            scalars=lambda: type("S", (), {"all": staticmethod(lambda: [])})(),
        )

        keys: list[str] = []

        async def fake_get(key):
            keys.append(key)
            return None

        async def fake_set(key, value, ttl=None):
            keys.append(key)

        with patch.object(analytics, "cache_get", new=fake_get), \
             patch.object(analytics, "cache_set", new=fake_set):
            await analytics.get_summary(current_user=seller, db=db)
            await analytics.get_chat_stats(days=30, current_user=seller, db=db)
            await analytics.get_conversion_funnel(days=30, current_user=seller, db=db)
            await analytics.get_campaign_roi(campaign_id=0, current_user=seller, db=db)
            await analytics.get_product_insights(current_user=seller, db=db)

        return keys

    async def test_analytics_cache_keys_are_seller_scoped(self):
        keys_a = await self._keys_for_seller(1)
        keys_b = await self._keys_for_seller(2)

        self.assertTrue(keys_a, "no analytics cache keys were produced")
        self.assertEqual(set(), set(keys_a) & set(keys_b), "cache keys shared across sellers")
        for key in keys_a:
            self.assertTrue(key.startswith("analytics:1:"), key)
        for key in keys_b:
            self.assertTrue(key.startswith("analytics:2:"), key)

    async def test_cache_keys_include_period_parameter(self):
        import api.routes_analytics as analytics

        seller = type("Seller", (), {"id": 9})()
        db = AsyncMock()
        db.execute.return_value = AsyncMock(scalar=lambda: 0, all=lambda: [])

        keys: list[str] = []

        async def fake_get(key):
            keys.append(key)
            return None

        async def fake_set(key, value, ttl=None):
            pass

        with patch.object(analytics, "cache_get", new=fake_get), \
             patch.object(analytics, "cache_set", new=fake_set):
            await analytics.get_chat_stats(days=7, current_user=seller, db=db)
            await analytics.get_chat_stats(days=30, current_user=seller, db=db)

        self.assertEqual(len(set(keys)), 2, keys)
        self.assertIn("analytics:9:chat-stats:7", keys)
        self.assertIn("analytics:9:chat-stats:30", keys)

    async def test_admin_stats_cache_key_is_not_seller_scoped_and_stable(self):
        import api.routes_admin as admin

        # Admin /stats is platform-wide; a stable, tenant-free key is correct here.
        self.assertEqual(admin.ADMIN_STATS_CACHE_KEY, "analytics:admin:stats")
        self.assertLessEqual(admin.ADMIN_STATS_TTL, 60)


class GZipStreamingExclusionTests(unittest.TestCase):
    def test_starlette_gzip_excludes_event_stream(self):
        """SSE must bypass GZip buffering; rely on starlette's exclusion list."""
        from starlette.middleware.gzip import DEFAULT_EXCLUDED_CONTENT_TYPES

        self.assertIn("text/event-stream", DEFAULT_EXCLUDED_CONTENT_TYPES)


if __name__ == "__main__":
    unittest.main()

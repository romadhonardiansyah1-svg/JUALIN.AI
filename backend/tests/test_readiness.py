import json
import unittest
from unittest.mock import AsyncMock, patch

import main
from starlette.responses import JSONResponse


class _FailingSessionContext:
    async def __aenter__(self):
        raise ConnectionError('database unavailable')

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _HealthySession:
    async def execute(self, statement):
        return None


class _HealthySessionContext:
    async def __aenter__(self):
        return _HealthySession()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _HealthyRedis:
    async def ping(self):
        return True


class ReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_readiness_returns_503_when_database_is_unavailable(self):
        with (
            patch.object(main, 'async_session', return_value=_FailingSessionContext()),
            patch('cache.get_redis', new=AsyncMock(return_value=_HealthyRedis())),
            patch.object(main.logger, 'warning') as log_warning,
        ):
            response = await main.readiness()

        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 503)
        body = json.loads(response.body)
        self.assertEqual(body['ready'], False)
        self.assertEqual(body['errors'], ['database'])
        log_warning.assert_called_once_with(
            'Database readiness check failed',
            exc_info=True,
        )

    async def test_readiness_returns_503_when_redis_is_unavailable(self):
        with (
            patch.object(main, 'async_session', return_value=_HealthySessionContext()),
            patch('cache.get_redis', new=AsyncMock(return_value=None)),
            patch.object(main.logger, 'warning') as log_warning,
        ):
            response = await main.readiness()

        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 503)
        body = json.loads(response.body)
        self.assertEqual(body['ready'], False)
        self.assertEqual(body['errors'], ['redis'])
        log_warning.assert_called_once_with(
            'Redis readiness check failed: client unavailable',
        )

    async def test_readiness_keeps_success_response_compatible(self):
        with (
            patch.object(main, 'async_session', return_value=_HealthySessionContext()),
            patch('cache.get_redis', new=AsyncMock(return_value=_HealthyRedis())),
        ):
            response = await main.readiness()

        self.assertEqual(response, {'ready': True})

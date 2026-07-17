import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
from fastapi import HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials

from api import routes_auth


class AuthTokenTests(unittest.IsolatedAsyncioTestCase):
    def test_access_token_preserves_required_claims(self):
        token = routes_auth.create_access_token(
            42,
            impersonation=True,
            impersonated_by=7,
            target_seller_id=42,
        )

        payload = jwt.decode(
            token,
            routes_auth.settings.JWT_SECRET_KEY,
            algorithms=[routes_auth.settings.JWT_ALGORITHM],
        )

        self.assertEqual(payload['sub'], '42')
        self.assertEqual(payload['token_type'], 'access')
        self.assertTrue(payload['impersonation'])
        self.assertEqual(payload['impersonated_by'], 7)
        self.assertEqual(payload['target_seller_id'], 42)
        self.assertTrue(payload['jti'])
        self.assertIn('exp', payload)

    async def test_invalid_token_is_rejected_before_database_lookup(self):
        credentials = HTTPAuthorizationCredentials(
            scheme='Bearer',
            credentials='not-a-jwt',
        )
        database = AsyncMock()
        request = SimpleNamespace(state=SimpleNamespace())

        with self.assertRaises(HTTPException) as raised:
            await routes_auth.get_current_user(request, credentials, database)

        self.assertEqual(raised.exception.status_code, 401)
        database.execute.assert_not_awaited()


    def test_browser_access_token_is_short_lived_and_session_bound(self):
        session_id = uuid.uuid4()
        token = routes_auth.create_access_token(42, session_id=session_id)
        payload = jwt.decode(
            token,
            routes_auth.settings.JWT_SECRET_KEY,
            algorithms=[routes_auth.settings.JWT_ALGORITHM],
        )

        self.assertEqual(payload["sid"], str(session_id))
        remaining = datetime.fromtimestamp(payload["exp"], timezone.utc) - datetime.now(timezone.utc)
        self.assertLessEqual(remaining.total_seconds(), 16 * 60)

    def test_auth_response_does_not_expose_raw_access_token(self):
        self.assertNotIn("access_token", routes_auth.TokenResponse.model_fields)

    async def test_refresh_rotation_locks_the_presented_session(self):
        from services.auth_session_service import rotate_refresh_token

        old_session = SimpleNamespace(revoked_at=datetime.now(timezone.utc), is_current=True)
        query_result = MagicMock()
        query_result.scalar_one_or_none.return_value = old_session
        database = AsyncMock()
        database.execute.return_value = query_result

        result = await rotate_refresh_token(database, old_refresh_token="old-refresh")

        self.assertEqual(result, (None, "", "", "invalid"))
        query = database.execute.await_args.args[0]
        self.assertIn("FOR UPDATE", str(query).upper())

    async def test_failed_initial_session_rolls_back_registration(self):
        database = AsyncMock()
        database.add = MagicMock()
        query_result = MagicMock()
        query_result.scalar_one_or_none.return_value = None
        database.execute.return_value = query_result
        request = Request(
            {"type": "http", "headers": [], "client": ("127.0.0.1", 1234)}
        )
        response = Response()
        registration = routes_auth.RegisterRequest(
            email="seller@example.com",
            password="long-enough-password",
            nama_toko="Toko Aman",
        )

        with (
            patch(
                "core.rate_limit.check_rate_limit",
                new=AsyncMock(return_value={"allowed": True}),
            ),
            patch.object(routes_auth, "_record_auth_audit", new=AsyncMock()),
            patch.object(
                routes_auth,
                "create_session_family",
                new=AsyncMock(side_effect=RuntimeError("session unavailable")),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await routes_auth.register(
                    registration, request, response, database
                )

        self.assertEqual(raised.exception.status_code, 503)
        database.rollback.assert_awaited_once()
        database.commit.assert_not_awaited()

    async def test_recent_parallel_refresh_does_not_revoke_rotated_family(self):
        from services import auth_session_service

        old_session = SimpleNamespace(
            revoked_at=None,
            is_current=False,
            last_used_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            absolute_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            family_id=uuid.uuid4(),
        )
        query_result = MagicMock()
        query_result.scalar_one_or_none.return_value = old_session
        database = AsyncMock()
        database.execute.return_value = query_result

        with patch.object(
            auth_session_service, "_revoke_family", new=AsyncMock()
        ) as revoke_family:
            result = await auth_session_service.rotate_refresh_token(
                database, old_refresh_token="old-refresh"
            )

        self.assertEqual(result, (None, "", "", "already_rotated"))
        revoke_family.assert_not_awaited()
        database.commit.assert_not_awaited()

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jwt
from fastapi import HTTPException
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

"""Regression coverage for the chat -> order transaction and chat history IDOR."""
import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request


class _Savepoint:
    """Minimal savepoint double: reverts recorded attribute state on failure."""

    def __init__(self, snapshot_targets):
        self._targets = snapshot_targets
        self._snapshot = None
        self.rolled_back = False

    async def __aenter__(self):
        self._snapshot = [(t, t.stok) for t in self._targets]
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            for target, stok in self._snapshot:
                target.stok = stok
            self.rolled_back = True
        return False


class ChatOrderTransactionTests(unittest.IsolatedAsyncioTestCase):
    def _product(self):
        return SimpleNamespace(id=5, nama="Baju Pink", stok=3, harga=89000)

    def _db(self, product):
        product_result = MagicMock()
        product_result.scalars.return_value.all.return_value = [product]
        db = AsyncMock()
        db.add = MagicMock()
        db.execute.return_value = product_result
        savepoint = _Savepoint([product])
        db.begin_nested = MagicMock(return_value=savepoint)
        return db, savepoint

    async def test_stock_mutation_is_scoped_to_a_savepoint(self):
        from ai import tools

        source = inspect.getsource(tools.tool_buat_order)
        savepoint_at = source.index("db.begin_nested()")
        mutation_at = source.index("p.stok -= it.get")
        commit_at = source.index("await db.commit()")
        self.assertLess(savepoint_at, mutation_at, "stok dimutasi di luar savepoint")
        self.assertLess(mutation_at, commit_at)

    async def test_failed_order_creation_leaves_no_uncommitted_stock_mutation(self):
        from ai import tools

        product = self._product()
        db, savepoint = self._db(product)

        with patch.object(tools, "Order", side_effect=RuntimeError("insert failed")):
            with self.assertRaises(RuntimeError):
                await tools.tool_buat_order(
                    seller_id=1,
                    customer_name="Budi",
                    customer_phone="0812",
                    customer_address="Jl. Mawar",
                    items=[{"product_id": 5, "nama": "Baju Pink", "qty": 2, "harga": 89000}],
                    conversation_id=7,
                    db=db,
                )

        self.assertTrue(savepoint.rolled_back)
        self.assertEqual(product.stok, 3, "potongan stok bocor ke session pemanggil")
        db.commit.assert_not_awaited()

    async def test_validation_error_returns_without_stock_mutation_or_commit(self):
        from ai import tools

        product = self._product()
        db, _ = self._db(product)

        result = await tools.tool_buat_order(
            seller_id=1,
            customer_name="Budi",
            customer_phone="0812",
            customer_address="Jl. Mawar",
            items=[{"product_id": 5, "nama": "Baju Pink", "qty": 99, "harga": 89000}],
            conversation_id=7,
            db=db,
        )

        self.assertIn("error", result)
        self.assertEqual(product.stok, 3)
        db.commit.assert_not_awaited()

    async def test_successful_order_does_not_refresh_after_commit(self):
        from ai import tools

        product = self._product()
        db, _ = self._db(product)

        def assign_id(order):
            order.id = 42

        db.add.side_effect = assign_id

        result = await tools.tool_buat_order(
            seller_id=1,
            customer_name="Budi",
            customer_phone="0812",
            customer_address="Jl. Mawar",
            items=[{"product_id": 5, "nama": "Baju Pink", "qty": 2, "harga": 89000}],
            conversation_id=7,
            db=db,
        )

        self.assertEqual(result["order_id"], 42)
        self.assertEqual(product.stok, 1)
        db.commit.assert_awaited_once()
        db.refresh.assert_not_awaited()


class ChatHistoryAccessTests(unittest.IsolatedAsyncioTestCase):
    def _request(self):
        return Request({
            "type": "http", "method": "GET", "path": "/api/chat/history/guessed",
            "headers": [], "client": ("127.0.0.1", 1234),
        })

    async def test_guessed_session_id_alone_cannot_read_history(self):
        from api.routes_chat import get_chat_history

        db = AsyncMock()
        with (
            patch("core.rate_limit.check_rate_limit", new=AsyncMock(return_value={"allowed": True})),
            patch("api.routes_chat.get_current_user",
                  new=AsyncMock(side_effect=HTTPException(status_code=401, detail="Token tidak valid"))),
        ):
            with self.assertRaises(HTTPException) as raised:
                await get_chat_history("cust-1700000000000-abc123xyz", self._request(), None, db)

        self.assertEqual(raised.exception.status_code, 403)
        db.execute.assert_not_awaited()

    async def test_anonymous_history_lookup_is_scoped_to_the_seller(self):
        from api.routes_chat import get_chat_history

        slug_result = MagicMock()
        slug_result.scalar_one_or_none.return_value = 9
        conversation_result = MagicMock()
        conversation_result.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute.side_effect = [slug_result, conversation_result]

        with (
            patch("core.rate_limit.check_rate_limit", new=AsyncMock(return_value={"allowed": True})),
            patch("api.routes_chat.get_current_user",
                  new=AsyncMock(side_effect=HTTPException(status_code=401, detail="Token tidak valid"))),
        ):
            with self.assertRaises(HTTPException) as raised:
                await get_chat_history("cust-1700000000000-abc123xyz", self._request(), "toko-lain", db)

        self.assertEqual(raised.exception.status_code, 404)
        statement = str(db.execute.await_args_list[1].args[0]).lower()
        self.assertIn("conversations.seller_id", statement)
        self.assertIn("conversations.session_id", statement)

    async def test_history_is_rate_limited_per_ip(self):
        from api.routes_chat import get_chat_history

        db = AsyncMock()
        with patch("core.rate_limit.check_rate_limit",
                   new=AsyncMock(return_value={"allowed": False})) as limiter:
            with self.assertRaises(HTTPException) as raised:
                await get_chat_history("cust-1700000000000-abc123xyz", self._request(), "toko", db)

        self.assertEqual(raised.exception.status_code, 429)
        limiter.assert_awaited_once()
        db.execute.assert_not_awaited()


class QuotaMessagePrivacyTests(unittest.IsolatedAsyncioTestCase):
    def test_quota_exceeded_messages_do_not_leak_seller_phone(self):
        from api import routes_chat, routes_chat_stream

        self.assertNotIn("seller.no_hp", inspect.getsource(routes_chat.send_message))
        self.assertNotIn("seller.no_hp", inspect.getsource(routes_chat_stream.stream_chat))


if __name__ == "__main__":
    unittest.main()

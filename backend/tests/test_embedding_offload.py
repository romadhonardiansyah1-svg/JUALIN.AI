"""Regression: chat hot-path embedding must run off the event loop thread.

`generate_embedding` loads SentenceTransformer (torch) and runs CPU inference.
Calling it directly inside `async def` blocks the whole FastAPI process.
These tests assert the sync work lands on a worker thread, not MainThread.
"""
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


def _thread_recorder(calls):
    def fake_generate_embedding(text):
        calls.append(threading.current_thread().name)
        return [0.0, 0.0, 0.0]

    return fake_generate_embedding


def _empty_db():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db = AsyncMock()
    db.execute.return_value = result
    return db


class EmbeddingOffloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_semantic_search_offloads_embedding(self):
        from ai.agent import search_products_semantic

        calls = []
        db = _empty_db()
        with patch("ai.embeddings.generate_embedding", _thread_recorder(calls)):
            await search_products_semantic("baju pink", seller_id=1, db=db)

        self.assertEqual(len(calls), 1, "embedding not called — search fell back")
        self.assertNotEqual(calls[0], threading.main_thread().name)

    async def test_tool_cari_produk_offloads_embedding(self):
        from ai.tools import tool_cari_produk

        calls = []
        db = _empty_db()
        with patch("ai.embeddings.generate_embedding", _thread_recorder(calls)):
            await tool_cari_produk("baju pink", seller_id=1, db=db)

        self.assertEqual(len(calls), 1)
        self.assertNotEqual(calls[0], threading.main_thread().name)


if __name__ == "__main__":
    unittest.main()

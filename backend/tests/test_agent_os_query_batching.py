"""Lock query batching (no N+1) in agent_os hot paths, with behaviour unchanged."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


def _scalars_result(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _product(pid, nama, stok, is_active=1):
    return SimpleNamespace(id=pid, nama=nama, stok=stok, is_active=is_active)


class CheckStockGuardBatchingTests(unittest.IsolatedAsyncioTestCase):
    async def test_five_items_use_single_query(self):
        from services.agent_os.inventory import check_stock_guard

        products = [_product(i, f"Produk {i}", 10) for i in range(1, 6)]
        db = AsyncMock()
        db.execute.return_value = _scalars_result(products)

        out = await check_stock_guard(7, [{"product_id": p.id, "qty": 1} for p in products], db)

        self.assertEqual(db.execute.await_count, 1)
        self.assertEqual(out, {"ok": True, "issues": []})

    async def test_missing_and_inactive_product_reported_as_not_found(self):
        from services.agent_os.inventory import check_stock_guard

        db = AsyncMock()
        db.execute.return_value = _scalars_result([_product(2, "Nonaktif", 10, is_active=0)])

        out = await check_stock_guard(7, [
            {"product_id": 1, "qty": 1},   # tidak ada di DB
            {"product_id": 2, "qty": 1},   # ada tapi is_active != 1
        ], db)

        self.assertFalse(out["ok"])
        self.assertEqual(out["issues"], [
            {"product_id": 1, "reason": "tidak ditemukan"},
            {"product_id": 2, "reason": "tidak ditemukan"},
        ])

    async def test_insufficient_stock_keeps_same_issue_shape(self):
        from services.agent_os.inventory import check_stock_guard

        db = AsyncMock()
        db.execute.return_value = _scalars_result([_product(3, "Kopi", 2)])

        out = await check_stock_guard(7, [{"product_id": 3, "qty": 5}], db)

        self.assertEqual(out, {
            "ok": False,
            "issues": [{"product_id": 3, "nama": "Kopi", "reason": "stok 2 < 5"}],
        })

    async def test_items_without_product_id_are_skipped_without_query(self):
        from services.agent_os.inventory import check_stock_guard

        db = AsyncMock()

        out = await check_stock_guard(7, [{"qty": 2}, {"product_id": None}], db)

        self.assertEqual(db.execute.await_count, 0)
        self.assertEqual(out, {"ok": True, "issues": []})


class GetDealContextBatchingTests(unittest.IsolatedAsyncioTestCase):
    async def test_three_deals_use_single_product_query(self):
        from services.agent_os.negotiation import get_deal_context

        states = [SimpleNamespace(product_id=i, current_offer=1000 * i) for i in (1, 2, 3)]
        products = [_product(i, f"Produk {i}", 5) for i in (1, 2, 3)]
        db = AsyncMock()
        db.execute.side_effect = [_scalars_result(states), _scalars_result(products)]

        out = await get_deal_context(7, 42, db)

        self.assertEqual(db.execute.await_count, 2)  # 1 state + 1 produk (batched)
        for i in (1, 2, 3):
            self.assertIn(f"- Produk {i}: SUDAH DEAL di Rp {1000 * i:,.0f}", out)

    async def test_deal_with_missing_product_is_skipped(self):
        from services.agent_os.negotiation import get_deal_context

        states = [
            SimpleNamespace(product_id=1, current_offer=5000),
            SimpleNamespace(product_id=99, current_offer=7000),   # produk terhapus
            SimpleNamespace(product_id=2, current_offer=0),       # tanpa offer
        ]
        db = AsyncMock()
        db.execute.side_effect = [
            _scalars_result(states),
            _scalars_result([_product(1, "Teh", 5), _product(2, "Gula", 5)]),
        ]

        out = await get_deal_context(7, 42, db)

        self.assertIn("- Teh: SUDAH DEAL di Rp 5,000", out)
        self.assertNotIn("Gula", out)
        self.assertEqual(out.count("SUDAH DEAL"), 1)

    async def test_no_accepted_deal_returns_empty_string_without_product_query(self):
        from services.agent_os.negotiation import get_deal_context

        db = AsyncMock()
        db.execute.side_effect = [_scalars_result([])]

        out = await get_deal_context(7, 42, db)

        self.assertEqual(out, "")
        self.assertEqual(db.execute.await_count, 1)


if __name__ == "__main__":
    unittest.main()

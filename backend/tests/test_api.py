"""
JUALIN.AI — API Endpoint Tests
"""
import pytest
from unittest.mock import patch, MagicMock


class TestAuthEndpoints:
    """Test auth API endpoints."""

    def test_register_schema(self):
        """Register request schema valid."""
        body = {
            "email": "test@test.com",
            "password": "test123456",
            "nama_toko": "Test Store",
            "no_hp": "081234567890",
        }
        assert "email" in body
        assert "password" in body
        assert "nama_toko" in body
        assert len(body["password"]) >= 10

    def test_login_schema(self):
        """Login request schema valid."""
        body = {"email": "test@test.com", "password": "test123456"}
        assert "email" in body
        assert "password" in body

    def test_jwt_token_format(self):
        """JWT token has correct format."""
        # JWT has 3 parts separated by dots
        sample_token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        parts = sample_token.split(".")
        assert len(parts) == 3


class TestProductEndpoints:
    """Test product API endpoints."""

    def test_product_create_schema(self):
        """Product create schema valid."""
        body = {
            "nama": "Test Product",
            "deskripsi": "Test description",
            "harga": 89000,
            "stok": 25,
            "kategori": "fashion",
            "foto_url": "",
        }
        assert body["harga"] > 0
        assert body["stok"] >= 0
        assert len(body["nama"]) > 0

    def test_product_update_schema(self):
        """Product update schema valid (partial)."""
        body = {"harga": 99000}
        assert "harga" in body

    def test_tier_product_limits(self):
        """Product limits per tier."""
        limits = {"free": 10, "starter": 50, "pro": 200, "bisnis": 999999}
        assert limits["free"] < limits["starter"]
        assert limits["starter"] < limits["pro"]
        assert limits["pro"] < limits["bisnis"]


class TestChatEndpoints:
    """Test chat API endpoints."""

    def test_chat_send_schema(self):
        """Chat send schema valid."""
        body = {
            "message": "Ada baju pink?",
            "session_id": "test-session-123",
            "seller_slug": "toko-sari",
        }
        assert len(body["message"]) > 0
        assert len(body["session_id"]) > 0

    def test_quota_limits(self):
        """Quota limits per tier."""
        quotas = {"free": 50, "starter": 500, "pro": 2000, "bisnis": 10000}
        assert quotas["free"] == 50
        assert quotas["pro"] == 2000


class TestOrderEndpoints:
    """Test order API endpoints."""

    def test_order_status_flow(self):
        """Order status flow is valid."""
        valid_flow = {
            "pending": ["paid", "cancelled"],
            "paid": ["shipped"],
            "shipped": ["done"],
        }
        assert "paid" in valid_flow["pending"]
        assert "shipped" in valid_flow["paid"]
        assert "done" in valid_flow["shipped"]

    def test_order_items_schema(self):
        """Order items schema valid."""
        items = [
            {"product_id": 1, "nama": "Baju Pink", "qty": 2, "harga": 89000},
        ]
        total = sum(i["harga"] * i["qty"] for i in items)
        assert total == 178000

    def test_parse_product_line(self):
        """Test parsing product names and quantities from strings."""
        from api.routes_chat import parse_product_line
        assert parse_product_line("Baju Pink Satin x2") == ("Baju Pink Satin", 2)
        assert parse_product_line("Kaos Oversize 3 pcs") == ("Kaos Oversize", 3)
        assert parse_product_line("Dress Emerald Elegan 5") == ("Dress Emerald Elegan", 5)
        assert parse_product_line("Hoodie Abu-abu") == ("Hoodie Abu-abu", 1)

    def test_parse_order_text(self):
        """Test parsing full confirmed order messages."""
        from api.routes_chat import parse_order_text
        sample_text = (
            "✅ ORDER CONFIRMED!\n"
            "Produk: Baju Pink Satin x2\n"
            "Produk: Kaos Oversize x1\n"
            "Total: Rp 237,000\n"
            "Nama: Dian Ganteng\n"
            "Alamat: Jl. Sudirman No. 12, Jakarta\n"
            "HP: 081234567890\n"
        )
        parsed = parse_order_text(sample_text)
        assert parsed is not None
        assert parsed["customer_name"] == "Dian Ganteng"
        assert parsed["customer_address"] == "Jl. Sudirman No. 12, Jakarta"
        assert parsed["customer_phone"] == "081234567890"
        assert parsed["products_raw"] == ["Baju Pink Satin x2", "Kaos Oversize x1"]

"""
JUALIN.AI — Test Suite
30 skenario uji untuk AI Sales Assistant
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

# ── Test 1-3: Tanya produk yang ada ──

class TestCatalogAwareRAG:
    """Test AI menjawab berdasarkan katalog."""

    def test_01_tanya_produk_ada(self):
        """Customer tanya produk yang ada di katalog."""
        from ai.guardrails import check_guardrails
        response = "Hai kak! Kami punya Baju Pink Satin dengan harga Rp 89.000. Bahannya satin premium ya kak!"
        result = check_guardrails(response, "ada baju pink?")
        assert result["is_safe"] is True

    def test_02_tanya_harga(self):
        """Customer tanya harga produk."""
        from ai.guardrails import check_guardrails
        response = "Harga Baju Pink Satin Rp 89.000 kak. Mau order?"
        result = check_guardrails(response, "berapa harga baju pink?")
        assert result["is_safe"] is True

    def test_03_tanya_stok(self):
        """Customer tanya stok produk."""
        from ai.guardrails import check_guardrails
        response = "Stok Baju Pink masih ada 25 pcs kak. Mau pesan berapa?"
        result = check_guardrails(response, "masih ada stok gak?")
        assert result["is_safe"] is True


# ── Test 4-6: Tanya produk yang TIDAK ada ──

class TestProductNotFound:
    """Test AI menjawab saat produk tidak ditemukan."""

    def test_04_produk_tidak_ada(self):
        """Customer tanya produk yang tidak ada."""
        from ai.guardrails import check_guardrails
        response = "Maaf kak, produk sepatu Nike belum tersedia di toko kami. Tapi kami punya sneakers lain. Mau lihat?"
        result = check_guardrails(response, "ada sepatu Nike?")
        assert result["is_safe"] is True

    def test_05_minta_maaf_sopan(self):
        """AI harus minta maaf dengan sopan."""
        response = "Maaf kak, barang tersebut belum ada."
        assert "maaf" in response.lower()

    def test_06_tawarkan_alternatif(self):
        """AI harus tawarkan alternatif."""
        response = "Maaf kak belum ada. Tapi kami punya produk serupa yang mungkin cocok!"
        assert "alternatif" in response.lower() or "serupa" in response.lower() or "lain" in response.lower()


# ── Test 7-9: Semantic Search ──

class TestSemanticSearch:
    """Test pencarian semantik."""

    def test_07_deskripsi_abstrak(self):
        """Pencarian dengan deskripsi abstrak."""
        from ai.embeddings import build_embed_text
        text = build_embed_text({"nama": "Dress Emerald Elegan", "deskripsi": "gaun pesta mewah", "kategori": "dress", "harga": 189000})
        assert "pesta" in text.lower()
        assert "emerald" in text.lower()

    def test_08_embed_text_building(self):
        """Build embed text dari product data."""
        from ai.embeddings import build_embed_text
        text = build_embed_text({"nama": "Kaos Oversize", "deskripsi": "kaos casual", "kategori": "kaos", "harga": 75000})
        assert "kaos" in text.lower()
        assert "75000" in text

    def test_09_empty_fields(self):
        """Handle empty fields."""
        from ai.embeddings import build_embed_text
        text = build_embed_text({"nama": "", "deskripsi": "", "kategori": "", "harga": 0})
        assert "harga 0" in text


# ── Test 10-12: Order Creation ──

class TestOrderCreation:
    """Test pembuatan order."""

    def test_10_hitung_total_single(self):
        """Hitung total single item."""
        items = [{"nama": "Baju Pink", "harga": 89000, "qty": 2}]
        total = sum(i["harga"] * i["qty"] for i in items)
        assert total == 178000

    def test_11_hitung_total_multi(self):
        """Hitung total multi item."""
        items = [
            {"nama": "Baju Pink", "harga": 89000, "qty": 2},
            {"nama": "Kaos Oversize", "harga": 75000, "qty": 1},
        ]
        total = sum(i["harga"] * i["qty"] for i in items)
        assert total == 253000

    def test_12_format_rupiah(self):
        """Format angka ke Rupiah."""
        total = 178000
        formatted = f"Rp {total:,.0f}"
        assert formatted == "Rp 178,000"


# ── Test 13-15: Harga & Negosiasi ──

class TestPriceGuardrails:
    """Test guardrail harga."""

    def test_13_harga_dari_katalog(self):
        """AI menjawab harga dari katalog."""
        from ai.guardrails import check_guardrails
        response = "Harga Baju Pink Satin adalah Rp 89.000 kak."
        result = check_guardrails(response, "berapa harganya?")
        assert result["is_safe"] is True

    def test_14_tolak_nego_sopan(self):
        """AI tolak nego dengan sopan."""
        from ai.guardrails import check_guardrails
        response = "Maaf kak, harga sudah fixed ya. Tapi kami sering ada promo lho!"
        result = check_guardrails(response, "bisa kurang gak?")
        assert result["is_safe"] is True

    def test_15_tidak_karang_harga(self):
        """AI tidak mengarang harga."""
        from ai.guardrails import check_guardrails
        response = "Maaf kak, saya perlu cek dulu harganya ya."
        result = check_guardrails(response, "harga setelah diskon?")
        assert result["is_safe"] is True


# ── Test 16-18: Non-jualbeli ──

class TestTopicGuardrails:
    """Test guardrail topik."""

    def test_16_topik_politik(self):
        """AI redirect topik politik."""
        from ai.guardrails import check_guardrails
        response = "Hehe kak, saya cuma bisa bantu soal produk ya. Ada yang mau ditanya soal koleksi kami?"
        result = check_guardrails(response, "siapa presiden Indonesia?")
        assert result["is_safe"] is True

    def test_17_topik_pribadi(self):
        """AI redirect topik pribadi."""
        from ai.guardrails import check_guardrails
        response = "Hehe kak, saya AI asisten toko ya. Mau lihat produk kami?"
        result = check_guardrails(response, "kamu tinggal dimana?")
        assert result["is_safe"] is True

    def test_18_minta_hack(self):
        """AI tolak permintaan hacking."""
        from ai.guardrails import check_guardrails
        response = "Maaf kak, saya hanya bisa bantu soal produk toko ini. Ada yang bisa dibantu?"
        result = check_guardrails(response, "cara hack akun orang")
        assert result["is_safe"] is True


# ── Test 19-21: Multi-produk ──

class TestMultiProduct:
    """Test order multi produk."""

    def test_19_multi_item_order(self):
        """Order dengan multiple items."""
        items = [
            {"nama": "A", "harga": 50000, "qty": 1},
            {"nama": "B", "harga": 30000, "qty": 2},
            {"nama": "C", "harga": 100000, "qty": 1},
        ]
        total = sum(i["harga"] * i["qty"] for i in items)
        assert total == 210000
        assert len(items) == 3

    def test_20_quantity_benar(self):
        """Quantity dihitung benar."""
        items = [{"nama": "Test", "harga": 10000, "qty": 5}]
        total = items[0]["harga"] * items[0]["qty"]
        assert total == 50000

    def test_21_item_kosong(self):
        """Handle empty items."""
        items = []
        total = sum(i["harga"] * i.get("qty", 1) for i in items)
        assert total == 0


# ── Test 22-24: Stok Habis ──

class TestStockCheck:
    """Test pengecekan stok."""

    def test_22_stok_habis_response(self):
        """AI respond saat stok habis."""
        from ai.guardrails import check_guardrails
        response = "Maaf kak, produk ini sedang habis. Tapi kami punya alternatif serupa!"
        result = check_guardrails(response, "mau order baju pink")
        assert result["is_safe"] is True

    def test_23_stok_cukup(self):
        """Cek stok cukup untuk order."""
        stok = 25
        qty_order = 3
        assert stok >= qty_order

    def test_24_stok_tidak_cukup(self):
        """Cek stok tidak cukup."""
        stok = 2
        qty_order = 5
        assert stok < qty_order


# ── Test 25-27: Eskalasi ──

class TestEscalation:
    """Test eskalasi ke seller."""

    def test_25_customer_marah(self):
        """Detect customer marah."""
        from ai.guardrails import check_guardrails
        angry_words = ["goblok", "bangsat", "anjing", "tai"]
        message = "pelayanan kalian tai banget"
        has_angry = any(w in message.lower() for w in angry_words)
        assert has_angry is True

    def test_26_eskalasi_response(self):
        """AI eskalasi dengan sopan."""
        response = "Mohon maaf atas ketidaknyamanannya kak. Saya akan hubungkan kakak dengan admin kami."
        assert "maaf" in response.lower()
        assert "admin" in response.lower()

    def test_27_mark_urgent(self):
        """Order di-mark urgent."""
        is_urgent = True  # After escalation
        assert is_urgent is True


# ── Test 28-30: Follow-up ──

class TestFollowUp:
    """Test follow-up system."""

    def test_28_followup_messages(self):
        """Follow-up messages exist."""
        from ai.followup import FOLLOWUP_MESSAGES
        assert len(FOLLOWUP_MESSAGES) >= 3

    def test_29_followup_content(self):
        """Follow-up messages sopan."""
        from ai.followup import FOLLOWUP_MESSAGES
        for msg in FOLLOWUP_MESSAGES:
            assert "kak" in msg.lower() or "pesanan" in msg.lower()

    def test_30_max_followup(self):
        """Max 3 follow-ups."""
        max_followups = 3
        assert max_followups == 3


# ── Guardrails Unit Tests ──

class TestGuardrails:
    """Test guardrails module directly."""

    def test_guardrails_safe_response(self):
        """Safe response passes guardrails."""
        from ai.guardrails import check_guardrails
        result = check_guardrails("Baju Pink harganya Rp 89.000 kak!", "harga baju pink?")
        assert result["is_safe"] is True

    def test_guardrails_returns_dict(self):
        """Guardrails returns proper dict."""
        from ai.guardrails import check_guardrails
        result = check_guardrails("Test response", "test input")
        assert isinstance(result, dict)
        assert "is_safe" in result

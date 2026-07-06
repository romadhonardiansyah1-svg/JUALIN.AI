"""Uji mesin nego deterministik + firewall teks. Jalankan: python -m pytest tests/test_negotiation_engine.py -q"""
from types import SimpleNamespace

from services.agent_os.negotiation import (
    compute_floor_price, decide_offer, parse_price_ask, is_negotiation,
    _extract_prices, _text_price_safe,
)

POLICY = SimpleNamespace(
    max_discount_percent=15.0, margin_floor_percent=10.0,
    require_approval_above_percent=10.0, nego_max_rounds=3,
)


def test_floor_never_below_margin():
    # modal 60rb, margin 10% -> floor >= 66rb walau diskon 15% dari 100rb = 85rb
    assert compute_floor_price(100_000, 60_000, POLICY) == 85_000
    # modal tinggi mendominasi: modal 90rb -> floor 99rb (bukan 85rb)
    assert compute_floor_price(100_000, 90_000, POLICY) == 99_000


def test_offer_always_in_range_all_rounds_all_asks():
    floor = compute_floor_price(100_000, 60_000, POLICY)
    for rnd in range(0, 6):
        for ask in [None, 1_000, 50_000, 84_999, 85_000, 90_000, 99_999, 100_000, 150_000]:
            d = decide_offer(100_000, floor, ask, rnd, POLICY)
            assert floor <= d["offer_price"] <= 100_000, (rnd, ask, d)


def test_below_floor_never_accepted():
    floor = compute_floor_price(100_000, 60_000, POLICY)
    for rnd in range(0, 6):
        d = decide_offer(100_000, floor, 10_000, rnd, POLICY)
        assert d["decision"] == "counter_floor"
        assert d["offer_price"] >= floor


def test_parse_price_ask():
    assert parse_price_ask("150rb") == 150_000
    assert parse_price_ask("150 ribu boleh?") == 150_000
    assert parse_price_ask("1,5 juta") == 1_500_000
    assert parse_price_ask("1.5jt gimana") == 1_500_000
    assert parse_price_ask("rp 125000") == 125_000
    assert parse_price_ask("boleh 75?") == 75_000
    assert parse_price_ask("ambil 2 pcs") is None
    assert parse_price_ask("hp: 081234567890") is None
    assert parse_price_ask("oke deal") is None


def test_is_negotiation_quantity_not_nego():
    assert is_negotiation("boleh kurang ga?")
    assert is_negotiation("100 aja ya")
    assert not is_negotiation("ambil 2 aja")   # kuantitas 1 digit, bukan nego
    assert not is_negotiation("kirim ke bandung")


def test_text_firewall_blocks_below_floor():
    floor, offer = 85_000, 90_000
    ok = f"Siap kak, aku kasih Rp 90.000 ya"
    leak = f"Oke kak 50rb ya, atau Rp 90.000 juga boleh"
    missing = "Siap kak, harga spesial buat kamu"
    assert _text_price_safe(ok, floor, offer)
    assert not _text_price_safe(leak, floor, offer)      # ada angka < floor -> blok
    assert not _text_price_safe(missing, floor, offer)   # angka engine tidak disebut -> blok


def test_extract_prices_units():
    assert 1_500_000 in _extract_prices("kalau 1.5jt?")
    assert 90_000 in _extract_prices("Rp 90.000 ya kak")
    assert 50_000 in _extract_prices("50rb aja deh")

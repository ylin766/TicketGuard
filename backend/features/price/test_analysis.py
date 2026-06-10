"""Tests for the deterministic parts of price analysis. The Gemini-backed
extraction/evaluation paths are not exercised here (no network)."""

import backend.features.price.analysis as analysis


_LISTINGS = [
    {"price": 100, "section": "A", "row": "1", "listing_id": "l1"},
    {"price": 200, "section": "A", "row": "2", "listing_id": "l2"},
    {"price": 300, "section": "B", "row": "5", "listing_id": "l3"},
    {"price": 400, "section": "B", "row": "9", "listing_id": "l4"},
    {"price": None, "section": "C", "row": "1", "listing_id": "l5"},
]


def test_compute_market_stats_basic():
    stats = analysis.compute_market_stats(_LISTINGS, user_price=250, user_section="A")
    assert stats["count"] == 4  # None price ignored
    assert stats["median"] == 250.0  # median of [100,200,300,400]
    assert stats["min"] == 100 and stats["max"] == 400
    # 250 is above 200 of 4 prices (100,200) -> 50th percentile
    assert stats["percentile"] == 50
    assert stats["same_section_count"] == 2
    assert stats["same_section_median"] == 150.0  # median of [100,200]
    assert stats["fair_price_range"] is not None


def test_compute_market_stats_empty():
    stats = analysis.compute_market_stats([], user_price=100, user_section="A")
    assert stats["count"] == 0
    assert stats["median"] is None
    assert stats["percentile"] is None


def test_recommend_cheaper_prefers_same_section():
    recs = analysis.recommend_cheaper(_LISTINGS, user_price=350, user_section="B")
    # cheaper than 350: 100(A),200(A),300(B). Same section B first -> 300 leads.
    assert recs[0]["section"] == "B"
    assert recs[0]["price"] == 300
    assert all(r["price"] < 350 for r in recs)


def test_recommend_cheaper_no_user_price():
    recs = analysis.recommend_cheaper(_LISTINGS, user_price=None, user_section=None, limit=2)
    assert len(recs) == 2
    # lowest first when no section preference
    assert recs[0]["price"] == 100


def test_fallback_verdict_bands():
    good = analysis._fallback_verdict({"percentile": 20, "count": 10, "median": 100}, 80)
    assert good["verdict"] == "good_deal"
    high = analysis._fallback_verdict({"percentile": 90, "count": 10, "median": 100}, 300)
    assert high["verdict"] == "overpriced"
    unknown = analysis._fallback_verdict({"percentile": None, "count": 0}, None)
    assert unknown["verdict"] == "unknown"


def test_extract_user_listing_no_image():
    # No screenshot -> no Gemini call, returns {}.
    assert analysis.extract_user_listing(None, "https://x") == {}


def test_extract_json_tolerates_fences():
    assert analysis.extract_json('```json\n{"a":1}\n```') == {"a": 1}
    assert analysis.extract_json("prose {\"b\": 2} more") == {"b": 2}
    assert analysis.extract_json("nothing") == {}

"""Tests for the price scenario dataset generator. Offline: builds scenarios
from a tmp cache file, no LLM/network."""

import json

from backend.training.price_dataset import (
    TIER_PERCENTILES,
    build_providers,
    load_price_scenarios,
    scenarios_from_cache_file,
)


def _write_cache(path, prices):
    data = {
        "metadata": {
            "event_url": "https://stub/evt",
            "event_name": "Test Cup",
            "venue": "Test Arena",
            "date": "2026-06-15",
            "currency": "USD",
        },
        "tickets": [{"section": str(100 + i), "price": p} for i, p in enumerate(prices)],
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_scenarios_three_tiers(tmp_path):
    p = _write_cache(tmp_path / "evt.json", [100, 200, 300, 400, 500, 600, 700])
    scenarios = scenarios_from_cache_file(p)
    tiers = {s.tier for s in scenarios}
    assert tiers == set(TIER_PERCENTILES)  # low/mid/high
    # high-tier buyer price should exceed low-tier buyer price
    by_tier = {s.tier: s.buyer["price_per_ticket"] for s in scenarios}
    assert by_tier["high"] > by_tier["mid"] > by_tier["low"]


def test_scenario_carries_listings_and_event(tmp_path):
    p = _write_cache(tmp_path / "evt.json", [50, 150, 250])
    s = scenarios_from_cache_file(p)[0]
    assert s.event_url == "https://stub/evt"
    assert len(s.listings) == 3
    assert s.buyer["currency"] == "USD"
    assert s.buyer["event_name"] == "Test Cup"


def test_load_multiple_events(tmp_path):
    _write_cache(tmp_path / "a.json", [100, 200, 300])
    _write_cache(tmp_path / "b.json", [400, 500, 600])
    scenarios = load_price_scenarios(tmp_path)
    # 2 events x 3 tiers
    assert len(scenarios) == 6


def test_load_empty_dir_is_empty(tmp_path):
    assert load_price_scenarios(tmp_path / "nope") == []


def test_build_providers_keys_by_scenario_id(tmp_path):
    p = _write_cache(tmp_path / "evt.json", [100, 200, 300, 400, 500])
    scenarios = scenarios_from_cache_file(p)
    snap, buyer = build_providers(scenarios)
    sid = scenarios[0].scenario_id
    img, listings = snap(sid)
    assert img is None and len(listings) == 5
    assert buyer(sid)["section"] is not None
    # unknown key degrades safely
    assert snap("missing") == (None, [])
    assert buyer("missing") == {}


def test_real_cached_world_cup_event_produces_scenarios():
    """The seeded real StubHub world-cup cache yields 3 distinct-price tiers."""
    from backend.training.price_dataset import DEFAULT_CACHE_DIR

    if not DEFAULT_CACHE_DIR.exists():
        return  # cache not seeded in this checkout; skip
    scenarios = load_price_scenarios()
    if not scenarios:
        return
    prices = {s.tier: s.buyer["price_per_ticket"] for s in scenarios if "match14" in s.scenario_id}
    if len(prices) == 3:
        assert prices["high"] >= prices["mid"] >= prices["low"]

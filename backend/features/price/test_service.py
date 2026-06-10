"""Tests for the price service. These must NOT launch a real browser — the
scraper fetch functions are monkeypatched."""

import asyncio

import backend.features.price.service as service


def test_compute_median_empty():
    assert service.compute_median([]) is None


def test_compute_median_ignores_non_numeric():
    listings = [{"price": 100}, {"price": None}, {"price": "n/a"}, {"price": 300}]
    # median of [100, 300] = 200
    assert service.compute_median(listings) == 200.0


def test_compute_median_odd_even():
    assert service.compute_median([{"price": 50}]) == 50.0
    assert service.compute_median([{"price": 10}, {"price": 20}, {"price": 30}]) == 20.0
    assert service.compute_median([{"price": 10}, {"price": 30}]) == 20.0


def test_detect_source():
    assert service._detect_source("https://www.ticketmaster.com/x") == "ticketmaster"
    assert service._detect_source("https://www.stubhub.com/x") == "stubhub"
    assert service._detect_source("") == "stubhub"  # default


def test_normalize_url_adds_scheme():
    # Bare host (as the input field allows) gets https:// so Playwright accepts it.
    assert (
        service._normalize_url("stubhub.com/listing/98234?quantity=2")
        == "https://stubhub.com/listing/98234?quantity=2"
    )
    # Already-schemed URLs are left intact.
    assert service._normalize_url("https://x.com/e") == "https://x.com/e"
    assert service._normalize_url("http://x.com/e") == "http://x.com/e"
    # Leading slashes on a bare host are trimmed before prefixing.
    assert service._normalize_url("//stubhub.com/e") == "https://stubhub.com/e"
    assert service._normalize_url("") == ""


def test_stream_price_frames(monkeypatch):
    """stream_price emits start → frame(s) → analyzing → done, with a computed
    median, without launching a browser or calling Gemini (both are faked)."""

    async def fake_fetch(url, qty, on_frame=None):
        # Simulate the scraper emitting two screenshot frames.
        if on_frame:
            on_frame(0, b"\x89PNG-fake-0", "Opened event page")
            on_frame(1, b"\x89PNG-fake-1", "Extracted listings")
        return {
            "source": "stubhub",
            "metadata": {"event_name": "Test"},
            "listings": [{"price": 100}, {"price": 200}, {"price": 300}],
        }

    monkeypatch.setitem(service._FETCHERS, "stubhub", fake_fetch)

    # Fake the analysis layer so no real Gemini call is made.
    import backend.features.price.analysis as analysis

    def fake_analyze(image_bytes, url, listings, qty=2):
        return {
            "user_listing": {"section": "A", "price_per_ticket": 150},
            "stats": {"median": 200.0, "percentile": 40},
            "analysis": {"verdict": "good_deal", "headline": "ok"},
            "recommendations": [{"price": 100, "section": "A"}],
        }

    monkeypatch.setattr(analysis, "analyze", fake_analyze)

    async def run():
        frames = []
        async for f in service.stream_price("https://stubhub.com/e", 2):
            frames.append(f)
        return frames

    frames = asyncio.run(run())
    types = [f["type"] for f in frames]

    assert types[0] == "start"
    assert "frame" in types
    assert "analyzing" in types
    assert types[-1] == "done"

    done = frames[-1]
    assert done["count"] == 3
    assert done["median"] == 200.0
    assert done["analysis"]["verdict"] == "good_deal"
    assert done["recommendations"][0]["price"] == 100
    # frame events carry a base64 data-URL image
    frame_events = [f for f in frames if f["type"] == "frame"]
    assert frame_events and frame_events[0]["image"].startswith("data:image/png;base64,")

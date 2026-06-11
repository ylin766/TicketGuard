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

    def fake_analyze(image_bytes, url, listings, qty=2, user_listing=None):
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


def test_stream_price_resolver_path(monkeypatch):
    """A non-StubHub buyer URL triggers screenshot → vision extract → Tavily
    resolve → scrape the resolved reference event, then compare."""

    seen = {}

    async def fake_capture(url, on_frame=None, action="x"):
        if on_frame:
            on_frame(0, b"\x89PNG-user", action)
        return b"\x89PNG-user"

    def fake_extract(image_bytes, url):
        return {"event_name": "Spain vs Cape Verde", "section": "120"}

    def fake_resolve(user_listing, source):
        seen["resolved_event"] = user_listing.get("event_name")
        return "https://www.stubhub.com/world-cup-atlanta/event/153022393"

    async def fake_fetch(url, qty, on_frame=None):
        seen["scraped_url"] = url
        if on_frame:
            on_frame(1, b"\x89PNG-ref", "Opened event page")
        return {"source": "stubhub", "metadata": {}, "listings": [{"price": 400}]}

    def fake_analyze(image_bytes, url, listings, qty=2, user_listing=None):
        seen["analyze_user_listing"] = user_listing
        return {
            "user_listing": user_listing or {},
            "stats": {"median": 400.0},
            "analysis": {"verdict": "fair"},
            "recommendations": [],
        }

    import backend.features.price.capture as capture
    import backend.features.price.market_resolver as resolver
    import backend.features.price.analysis as analysis

    monkeypatch.setattr(capture, "capture_screenshot", fake_capture)
    monkeypatch.setattr(analysis, "extract_user_listing", fake_extract)
    monkeypatch.setattr(resolver, "resolve_market_url", fake_resolve)
    monkeypatch.setattr(analysis, "analyze", fake_analyze)
    monkeypatch.setitem(service._FETCHERS, "stubhub", fake_fetch)

    async def run():
        out = []
        async for f in service.stream_price(
            "https://www.boxofficeticketsales.com/123/spain-vs-cape-verde", 2
        ):
            out.append(f)
        return out

    frames = asyncio.run(run())
    done = frames[-1]

    assert done["type"] == "done"
    # The event Gemini read off the buyer page was passed to the resolver…
    assert seen["resolved_event"] == "Spain vs Cape Verde"
    # …the resolved StubHub URL was the one actually scraped…
    assert seen["scraped_url"].endswith("/event/153022393")
    # …and the pre-extracted user listing flowed into analyze.
    assert seen["analyze_user_listing"]["event_name"] == "Spain vs Cape Verde"
    assert done["analysis"]["verdict"] == "fair"


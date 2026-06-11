"""Price service: aggregate live market prices and stream the headed browser's
progress to the frontend.

Telemetry: the scrapers are deterministic (no LLM), so OpenInference's agent
instrumentation never sees them. We therefore wrap the run in a MANUAL
OpenTelemetry span (via the globally-configured TracerProvider from
``backend.observability.telemetry``), so the price collection still shows up in
the same Arize Phoenix workspace as the agent traces.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
from statistics import median as _median
from typing import AsyncGenerator

from .stubhub import fetch_stubhub
from .ticketmaster import fetch_ticketmaster

logger = logging.getLogger(__name__)

# Map a source name to its fetch function.
_FETCHERS = {
    "stubhub": fetch_stubhub,
    "ticketmaster": fetch_ticketmaster,
}


def _detect_source(url: str) -> str:
    u = (url or "").lower()
    if "ticketmaster" in u:
        return "ticketmaster"
    return "stubhub"  # default


def _reference_event(url: str) -> tuple[str, str] | None:
    """If ``url`` is already a StubHub/Ticketmaster page, return (source, url).

    Those are the marketplaces our scrapers can read, so we scrape them directly
    (no resolution detour). Any OTHER host is a buyer page we can't parse, so the
    caller must extract the event with vision and resolve a reference URL.
    """
    u = (url or "").lower()
    if "ticketmaster.com" in u:
        return ("ticketmaster", url)
    if "stubhub.com" in u:
        return ("stubhub", url)
    return None


def _normalize_url(url: str) -> str:
    """Ensure the URL has a scheme so Playwright can navigate to it.

    The input field accepts bare hosts (e.g. "stubhub.com/listing/98234"); add
    https:// when missing so ``page.goto`` doesn't reject an "invalid URL".
    """
    u = (url or "").strip()
    if not u:
        return u
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", u):
        u = "https://" + u.lstrip("/")
    return u


def compute_median(listings: list[dict]) -> float | None:
    """Median of the numeric ``price`` field across listings, or None if empty."""
    prices = [
        float(x["price"])
        for x in listings
        if isinstance(x, dict) and isinstance(x.get("price"), (int, float))
    ]
    if not prices:
        return None
    return float(_median(prices))


def _tracer():
    """Return an OTel tracer if telemetry is active, else None (no-op)."""
    try:
        from opentelemetry import trace

        # Ensure the central provider is initialized (idempotent).
        from ...observability.telemetry import init_telemetry

        init_telemetry()
        return trace.get_tracer("ticketguard.price")
    except Exception:  # noqa: BLE001 - telemetry must never break price
        return None


async def stream_price(url: str, qty: int = 2) -> AsyncGenerator[dict, None]:
    """Run the price scraper for ``url`` and yield SSE frames as it works.

    Frame contract (each yielded dict is one ``data:`` SSE line):
        {"type":"start","url":str,"source":str}
        {"type":"frame","step":int,"action":str,"image":"data:image/png;base64,…","ts":float}
        {"type":"analyzing","ts":float}
        {"type":"done","median":float|None,"count":int,"listings":[...],
         "user_listing":{...},"stats":{...},"analysis":{...},"recommendations":[...]}
        {"type":"error","message":str}
    """
    user_url = _normalize_url(url)
    yield {"type": "start", "url": user_url, "source": "stubhub"}

    # Bridge the scraper's synchronous-ish on_frame callback (called from the
    # scraper coroutine) into our async generator via a queue.
    queue: asyncio.Queue = asyncio.Queue()
    # Track the most recent screenshot so phase "status" frames (extract/resolve,
    # which produce no new shot) can reuse the last image to stay on the viewport.
    last_png: dict = {"bytes": None}

    def on_frame(step: int, png_bytes: bytes, action: str) -> None:
        if png_bytes:
            last_png["bytes"] = png_bytes
        b64 = base64.b64encode(png_bytes).decode("ascii") if png_bytes else ""
        queue.put_nowait(
            {
                "type": "frame",
                "step": step,
                "action": action,
                "image": f"data:image/png;base64,{b64}",
                "ts": time.time(),
            }
        )

    def emit_status(step: int, action: str) -> None:
        """Add a timeline step that reuses the last screenshot (no new shot)."""
        png = last_png["bytes"]
        if png:
            on_frame(step, png, action)

    tracer = _tracer()
    span_cm = (
        tracer.start_as_current_span("price.collect") if tracer else None
    )
    if span_cm is not None:
        span = span_cm.__enter__()
        try:
            span.set_attribute("price.url", user_url)
            span.set_attribute("price.qty", qty)
        except Exception:  # noqa: BLE001
            pass

    task: asyncio.Task | None = None
    user_listing: dict = {}
    try:
        # ------------------------------------------------------------------
        # Resolve which marketplace event to price against.
        #   * A StubHub/Ticketmaster URL is already readable -> scrape directly.
        #   * Any other host is a buyer page our scrapers can't parse, so we
        #     screenshot it, let Gemini read the event + seat, then search for
        #     the SAME event on a reference marketplace we can scrape.
        # ------------------------------------------------------------------
        direct = _reference_event(user_url)
        if direct is not None:
            ref_source, ref_url = direct
        else:
            ref_source = "stubhub"
            # Phase 1 — screenshot the buyer's page for vision.
            from .capture import capture_screenshot

            user_png = await capture_screenshot(
                user_url, on_frame, "Reading your ticket page"
            )
            while not queue.empty():
                yield queue.get_nowait()

            # Phase 2 — Gemini reads the buyer's event + seat off the page.
            user_listing = {}
            if user_png:
                from .analysis import extract_user_listing

                user_listing = (
                    await asyncio.to_thread(
                        extract_user_listing, user_png, user_url
                    )
                    or {}
                )
            ev_name = user_listing.get("event_name") or "this event"
            emit_status(1, f"Identified event · {ev_name}")
            while not queue.empty():
                yield queue.get_nowait()

            # Phase 3 — find the SAME event on the reference marketplace.
            emit_status(2, "Searching StubHub for the same match")
            while not queue.empty():
                yield queue.get_nowait()
            from .market_resolver import resolve_market_url

            ref_url = await asyncio.to_thread(
                resolve_market_url, user_listing, ref_source
            )
            # ref_url may be None -> the scraper falls back to its DEFAULT_URL.

        if span_cm is not None:
            try:
                span.set_attribute("price.source", ref_source)
                if ref_url:
                    span.set_attribute("price.reference_url", ref_url)
            except Exception:  # noqa: BLE001
                pass

        # ------------------------------------------------------------------
        # Phase 4 — scrape the reference marketplace event.
        # ------------------------------------------------------------------
        fetcher = _FETCHERS.get(ref_source, fetch_stubhub)
        task = asyncio.create_task(fetcher(ref_url, qty, on_frame))
        # Drain frames until the scrape task finishes and the queue is empty.
        while True:
            if task.done() and queue.empty():
                break
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=0.3)
                yield frame
            except asyncio.TimeoutError:
                continue

        result = await task
        listings = result.get("listings", [])
        med = compute_median(listings)
        if span_cm is not None:
            try:
                span.set_attribute("price.count", len(listings))
                if med is not None:
                    span.set_attribute("price.median", med)
            except Exception:  # noqa: BLE001
                pass

        # ------------------------------------------------------------------
        # Phase 5 — seat-view photos (local glob) + seat agent grading (Gemini).
        # Runs right after the scrape (only needs listings) so the seat unit
        # lights up before the market analysis. Emitted as a live "seat" step
        # stream so the frontend's seat unit shows a real agent trace. The agent
        # grades the buyer's own section plus a price-bracketed comparison set.
        # Best-effort: any failure degrades to photos-only and never breaks price.
        # ------------------------------------------------------------------
        try:
            from ..seats import attach_seat_photos, select_scoring_order
            from ..seats.agent import score_seat

            venue = (result.get("metadata") or {}).get("venue") or ""
            if venue:
                yield {
                    "type": "seat",
                    "action": "Matching sections to seat-view library",
                    "ts": time.time(),
                }
                local = await asyncio.to_thread(
                    attach_seat_photos, venue, listings
                )
                matched_sections = sorted(
                    {
                        str(listings[i].get("section"))
                        for i in local
                        if listings[i].get("section") is not None
                    }
                )
                yield {
                    "type": "seat",
                    "action": (
                        f"Found {len(matched_sections)} sections with real "
                        f"seat views"
                    ),
                    "ts": time.time(),
                }

                your_section = (user_listing or {}).get("section")
                order = select_scoring_order(
                    listings, local, 6, prioritize_section=your_section
                )
                if order:
                    yield {
                        "type": "seat",
                        "action": f"Grading {len(order)} seats with the agent",
                        "ts": time.time(),
                    }
                for idx in order:
                    sec = listings[idx].get("section")
                    urls = listings[idx].get("photo_urls") or []
                    yield {
                        "type": "seat",
                        "action": f"Grading section {sec} · sightline & value",
                        "image": urls[0] if urls else None,
                        "ts": time.time(),
                    }
                    price_val = listings[idx].get("price")
                    listings[idx]["seat_score"] = await asyncio.to_thread(
                        score_seat,
                        str(sec or ""),
                        local[idx],
                        price_val if isinstance(price_val, (int, float)) else None,
                        listings[idx].get("view"),
                    )
                yield {
                    "type": "seat",
                    "action": "Seat grading complete",
                    "ts": time.time(),
                }
        except Exception:  # noqa: BLE001 - seat photos/scores are best-effort
            logger.exception("[price] seat photo matching failed")

        # ------------------------------------------------------------------
        # Phase 6 — compare the buyer's ticket against the reference market.
        # ------------------------------------------------------------------
        yield {"type": "analyzing", "ts": time.time()}
        analysis_out: dict = {}
        try:
            from .analysis import analyze

            analysis_out = await asyncio.to_thread(
                analyze,
                last_png["bytes"],
                ref_url or user_url,
                listings,
                qty,
                user_listing or None,
            )
            if span_cm is not None:
                try:
                    verdict = (analysis_out.get("analysis") or {}).get("verdict")
                    if verdict:
                        span.set_attribute("price.verdict", verdict)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001 - analysis must never break the stream
            logger.exception("[price] analysis failed")

        yield {
            "type": "done",
            "median": med,
            "count": len(listings),
            "listings": listings,
            "metadata": result.get("metadata", {}),
            "user_listing": analysis_out.get("user_listing", {}),
            "same_seat": analysis_out.get("same_seat", {}),
            "stats": analysis_out.get("stats", {}),
            "analysis": analysis_out.get("analysis", {}),
            "recommendations": analysis_out.get("recommendations", []),
        }

    except Exception as exc:  # noqa: BLE001 - surface any failure as an error frame
        logger.exception("[price] stream failed")
        yield {"type": "error", "message": str(exc)}
    finally:
        # If the SSE client disconnected mid-scrape, the fetcher task (and its
        # headed browser) would otherwise keep running. Cancel it and let its own
        # try/finally close the browser. (We do NOT broadly sweep here: price and
        # the security browser-check can run concurrently, so killing all
        # descendant Chromium would take out the other flow's live browser.)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if span_cm is not None:
            span_cm.__exit__(None, None, None)

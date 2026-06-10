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
    source = _detect_source(url)
    fetcher = _FETCHERS.get(source, fetch_stubhub)
    url = _normalize_url(url)
    yield {"type": "start", "url": url, "source": source}

    # Bridge the scraper's synchronous-ish on_frame callback (called from the
    # scraper coroutine) into our async generator via a queue.
    queue: asyncio.Queue = asyncio.Queue()
    # Keep the first screenshot (the user's page as loaded) for vision extraction.
    first_shot: dict = {"bytes": None}

    def on_frame(step: int, png_bytes: bytes, action: str) -> None:
        if first_shot["bytes"] is None and png_bytes:
            first_shot["bytes"] = png_bytes
        b64 = base64.b64encode(png_bytes).decode("ascii")
        queue.put_nowait(
            {
                "type": "frame",
                "step": step,
                "action": action,
                "image": f"data:image/png;base64,{b64}",
                "ts": time.time(),
            }
        )

    tracer = _tracer()
    span_cm = (
        tracer.start_as_current_span("price.collect") if tracer else None
    )
    if span_cm is not None:
        span = span_cm.__enter__()
        try:
            span.set_attribute("price.source", source)
            span.set_attribute("price.url", url)
            span.set_attribute("price.qty", qty)
        except Exception:  # noqa: BLE001
            pass

    task = asyncio.create_task(fetcher(url, qty, on_frame))
    try:
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

        # Grounded analysis: extract the buyer's ticket (vision) + evaluate vs
        # market. Best-effort and off the event loop (blocking Gemini calls).
        yield {"type": "analyzing", "ts": time.time()}
        analysis_out: dict = {}
        try:
            from .analysis import analyze

            analysis_out = await asyncio.to_thread(
                analyze, first_shot["bytes"], url, listings, qty
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
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if span_cm is not None:
            span_cm.__exit__(None, None, None)

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
        {"type":"done","median":float|None,"count":int,"listings":[...],"metadata":{...}}
        {"type":"error","message":str}
    """
    source = _detect_source(url)
    fetcher = _FETCHERS.get(source, fetch_stubhub)
    yield {"type": "start", "url": url, "source": source}

    # Bridge the scraper's synchronous-ish on_frame callback (called from the
    # scraper coroutine) into our async generator via a queue.
    queue: asyncio.Queue = asyncio.Queue()

    def on_frame(step: int, png_bytes: bytes, action: str) -> None:
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
        yield {
            "type": "done",
            "median": med,
            "count": len(listings),
            "listings": listings,
            "metadata": result.get("metadata", {}),
        }
    except Exception as exc:  # noqa: BLE001 - surface any failure as an error frame
        logger.exception("[price] stream failed")
        yield {"type": "error", "message": str(exc)}
    finally:
        if span_cm is not None:
            span_cm.__exit__(None, None, None)

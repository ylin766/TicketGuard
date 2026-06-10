"""Threat-intel aggregator detector — deterministic, no LLM.

A lightweight, Docker-free replacement for a self-hosted IntelOwl: queries
several online sources in parallel and skips any source whose API key is unset.

Each source returns its own natural report (its fields are unique to that
source) and self-declares ``threat``:
  * True / False — a threat verdict (these go into ``findings``).
  * None         — a non-threat intelligence signal, e.g. domain age, geo,
                   popularity (these go into ``context`` and never flag).

The aggregator only collects those raw facts — it does not synthesize a score —
and sets ``flagged`` if any finding reported ``threat is True``.

Pure function: takes a URL, returns a normalized dict. No session state.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Generator

from .sources import ALL_SOURCES

logger = logging.getLogger(__name__)


def _query_source(source, url: str) -> dict | None:
    """Run one source; a None (skip) passes through, a failure becomes an error verdict."""
    try:
        return source.query(url)
    except Exception as exc:  # noqa: BLE001 - one bad source must not kill the rest
        logger.error("%s source failed: %s", getattr(source, "NAME", source), exc)
        return {"name": getattr(source, "NAME", "source"), "error": str(exc)}


def run_threatintel(url: str) -> dict:
    """Aggregate every configured source for a URL (blocking, returns all at once)."""
    with ThreadPoolExecutor(max_workers=len(ALL_SOURCES)) as pool:
        verdicts = list(pool.map(lambda s: _query_source(s, url), ALL_SOURCES))

    reported = [v for v in verdicts if v is not None and "error" not in v]
    if not reported:
        return {"status": "unavailable", "findings": [], "context": [],
                "flagged": False, "detail": "No source returned a result."}

    findings = [v for v in reported if v.get("threat") is not None]
    context = [v for v in reported if v.get("threat") is None]
    flagged = any(f["threat"] is True for f in findings)
    detail = " ".join(f"[{v['name']}] {v['detail']}" for v in reported)
    return {"status": "ok", "findings": findings, "context": context,
            "flagged": flagged, "detail": detail}


def stream_threatintel(url: str) -> Generator[dict, None, None]:
    """Stream source results one at a time as each completes.

    Yields one dict per source as soon as that source's query returns.
    Skipped sources (None) and errored sources are excluded.
    The final yielded item has type="done" and carries the aggregate summary.
    """
    reported: list[dict] = []

    with ThreadPoolExecutor(max_workers=len(ALL_SOURCES)) as pool:
        futures = {pool.submit(_query_source, src, url): src for src in ALL_SOURCES}

        for future in as_completed(futures):
            result = future.result()
            if result is None or "error" in result:
                continue
            reported.append(result)
            yield {"type": "source", "data": result}

    # Final summary event — carry the AUTHORITATIVE score + grey-zone decision so
    # the frontend gates the agent on the same logic the backend audit uses
    # (instead of re-deriving a verdict from raw alert counts).
    if not reported:
        yield {
            "type": "done",
            "status": "unavailable",
            "flagged": False,
            "score": None,
            "risk_level": None,
            "grey_zone": True,  # can't tell → escalate, same as the orchestrator
        }
        return

    findings = [r for r in reported if r.get("threat") is not None]
    context = [r for r in reported if r.get("threat") is None]
    flagged = any(f.get("threat") is True for f in findings)
    pipeline_result = {
        "status": "ok",
        "findings": findings,
        "context": context,
        "flagged": flagged,
    }
    try:
        from ..scoring import generate_score_breakdown
        from ..orchestrator import is_grey_zone

        breakdown = generate_score_breakdown(pipeline_result)
        grey = is_grey_zone(pipeline_result, breakdown["score"])
        yield {
            "type": "done",
            "status": "ok",
            "flagged": flagged,
            "score": breakdown["score"],
            "risk_level": breakdown["risk_level"],
            "grey_zone": grey,
        }
    except Exception as exc:  # noqa: BLE001 - never break the stream on scoring
        logger.warning("score breakdown failed in stream: %s", exc)
        yield {"type": "done", "status": "ok", "flagged": flagged,
               "score": None, "risk_level": None, "grey_zone": flagged}

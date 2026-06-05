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
from concurrent.futures import ThreadPoolExecutor

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
    """Aggregate every configured source for a URL.

    Args:
        url: The full ticket-listing URL to evaluate.

    Returns:
        dict with keys: status ("ok" | "unavailable"), findings (threat
        verdicts), context (non-threat intelligence), flagged (any finding
        reported a threat), detail.
    """
    with ThreadPoolExecutor(max_workers=len(ALL_SOURCES)) as pool:
        verdicts = list(pool.map(lambda s: _query_source(s, url), ALL_SOURCES))

    # None -> source skipped (no API key). A dict with "error" -> source failed.
    reported = [v for v in verdicts if v is not None and "error" not in v]
    if not reported:
        return {"status": "unavailable", "findings": [], "context": [],
                "flagged": False, "detail": "No source returned a result."}

    # threat is True/False -> a threat finding; None -> intelligence context.
    findings = [v for v in reported if v.get("threat") is not None]
    context = [v for v in reported if v.get("threat") is None]

    flagged = any(f["threat"] is True for f in findings)
    detail = " ".join(f"[{v['name']}] {v['detail']}" for v in reported)
    return {"status": "ok", "findings": findings, "context": context,
            "flagged": flagged, "detail": detail}

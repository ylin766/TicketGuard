"""Threat-intel aggregator detector — deterministic, no LLM.

A lightweight, Docker-free replacement for a self-hosted IntelOwl: queries
several online threat-intel sources in parallel and skips any source whose API
key is not configured.

Each source reports in its own natural form (a ``kind`` discriminator) and the
aggregator only collects those raw facts — it does not synthesize a score:
  * ``reputation_score`` — engine vote counts (VirusTotal).
  * ``blacklist_verdict`` — an authoritative listed/not-listed fact (Safe
    Browsing, URLhaus); a hit means the hit itself, not a number.

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


def _is_hit(finding: dict) -> bool:
    """Whether a source reported a threat (a listing or any non-clean engine vote)."""
    if finding["kind"] == "blacklist_verdict":
        return finding["listed"]
    if finding["kind"] == "reputation_score":
        return bool(finding["malicious"] or finding["suspicious"])
    return False


def run_threatintel(url: str) -> dict:
    """Aggregate every configured threat-intel source for a URL.

    Args:
        url: The full ticket-listing URL to evaluate.

    Returns:
        dict with keys: status ("ok" | "unavailable"), findings (each source's
        native report), flagged (any source reported a threat), detail.
    """
    with ThreadPoolExecutor(max_workers=len(ALL_SOURCES)) as pool:
        verdicts = list(pool.map(lambda s: _query_source(s, url), ALL_SOURCES))

    # None -> source skipped (no API key). "error" -> source failed.
    findings = [v for v in verdicts if v is not None and "kind" in v]
    if not findings:
        return {"status": "unavailable", "findings": [], "flagged": False,
                "detail": "No threat-intel source configured."}

    flagged = any(_is_hit(f) for f in findings)
    detail = " ".join(f"[{f['name']}] {f['detail']}" for f in findings)
    return {"status": "ok", "findings": findings, "flagged": flagged, "detail": detail}

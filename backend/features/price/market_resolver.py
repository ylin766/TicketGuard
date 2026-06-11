"""Resolve a user's event to the matching StubHub / Ticketmaster event URL.

The buyer may paste a listing from ANY site. To price-check it we need the same
event on a reference marketplace whose page our scrapers can read. Given the
event details Gemini extracted from the buyer's page (name + venue + date), we
search Tavily for "<event> site:stubhub.com" and take the best event-page hit.

Best-effort: returns None when nothing usable is found, so callers can fall back.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request

logger = logging.getLogger("ticketguard.price.resolver")

_TAVILY_URL = "https://api.tavily.com/search"

# A real StubHub/TM *event* page (not a category/performer/search page) has an
# "/event/<id>" segment — that's the only kind our scrapers can parse.
_EVENT_PATH_RE = re.compile(r"/event/[A-Za-z0-9]+", re.IGNORECASE)

_SITE_FOR = {
    "stubhub": "stubhub.com",
    "ticketmaster": "ticketmaster.com",
}


def _tavily_search(query: str, max_results: int = 6) -> list[dict]:
    key = os.environ.get("TAVILY_API_KEY", "")
    if not key:
        return []
    try:
        req = urllib.request.Request(
            _TAVILY_URL,
            data=json.dumps(
                {"api_key": key, "query": query, "max_results": max_results}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp).get("results", []) or []
    except Exception as exc:  # noqa: BLE001 - resolution is best-effort
        logger.warning("[price] tavily search failed: %s", str(exc)[:140])
        return []


def _build_query(user: dict) -> str | None:
    """Assemble a search query from the extracted user-listing fields."""
    parts = [
        user.get("event_name"),
        user.get("venue"),
        user.get("date"),
    ]
    q = " ".join(str(p) for p in parts if p)
    return q.strip() or None


def resolve_market_url(user: dict, source: str) -> str | None:
    """Find the ``source`` event URL matching the buyer's extracted event.

    Args:
        user: The vision-extracted user listing (needs at least ``event_name``).
        source: "stubhub" or "ticketmaster".

    Returns:
        A scraper-readable event-page URL, or None if none was found.
    """
    site = _SITE_FOR.get(source)
    query = _build_query(user)
    if not site or not query:
        return None

    results = _tavily_search(f"{query} site:{site}")
    # Prefer a genuine event page (has /event/<id>); fall back to the first
    # same-site result only if no event page is present.
    first_same_site = None
    for it in results:
        u = (it.get("url") or "").split("?")[0]
        if site not in u:
            continue
        if first_same_site is None:
            first_same_site = u
        if _EVENT_PATH_RE.search(u):
            return u
    return first_same_site

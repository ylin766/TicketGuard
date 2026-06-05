"""OpenPhish source — community phishing-URL feed (keyless).

Downloads the public OpenPhish feed (a plain list of phishing URLs), caches it
in-process, and checks whether the target URL is on it. A match is a threat.
"""

import logging
import threading
import time

import requests

from .....core.config import HTTP_TIMEOUT_SECONDS
from ..constants import OPENPHISH_CACHE_TTL_SECONDS, OPENPHISH_FEED_URL

logger = logging.getLogger(__name__)

NAME = "OpenPhish"

_lock = threading.Lock()
_cache: set[str] = set()
_cache_time = 0.0


def _feed() -> set[str]:
    """Return the phishing-URL set, refreshing the in-process cache on TTL expiry."""
    global _cache, _cache_time
    with _lock:
        if not _cache or time.monotonic() - _cache_time > OPENPHISH_CACHE_TTL_SECONDS:
            resp = requests.get(
                OPENPHISH_FEED_URL,
                headers={"User-Agent": "ticketguard/1.0"},
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            _cache = {line.strip() for line in resp.text.splitlines() if line.strip()}
            _cache_time = time.monotonic()
        return _cache


def query(url: str) -> dict | None:
    feed = _feed()
    listed = url in feed or url.rstrip("/") in feed
    return {
        "name": NAME,
        "threat": listed,
        "detail": (
            "URL is on the OpenPhish feed."
            if listed
            else f"Not on the OpenPhish feed ({len(feed)} entries checked)."
        ),
    }

"""Tranco source — domain popularity rank (a credibility signal, not a threat).

Tranco ranks registered domains by popularity (a smaller rank = more popular,
so more likely to be a legitimate, established site). This is context for the
grey-zone agent, NOT a threat verdict, so it never sets the ``flagged`` bit.

Public endpoint, no API key required, so this source has no env var.
"""

import logging
from urllib.parse import urlparse

import requests

from .....core.config import HTTP_TIMEOUT_SECONDS
from ..constants import TRANCO_API_BASE

logger = logging.getLogger(__name__)

NAME = "Tranco"


def _registered_domain(url: str) -> str:
    """Best-effort registered domain: host without a leading ``www.``."""
    host = urlparse(url).netloc or url
    return host[4:] if host.startswith("www.") else host


def query(url: str) -> dict | None:
    domain = _registered_domain(url)
    resp = requests.get(
        f"{TRANCO_API_BASE}/{domain}",
        headers={"User-Agent": "ticketguard/1.0"},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    ranks = resp.json().get("ranks") or []
    rank = ranks[0].get("rank") if ranks else None
    return {
        "name": NAME,
        # Credibility signal, not a threat detector: threat is always None.
        "threat": None,
        "rank": rank,
        "detail": (
            f"{domain} ranks #{rank} on the Tranco popularity list."
            if rank is not None
            else f"{domain} is not on the Tranco popularity list."
        ),
    }

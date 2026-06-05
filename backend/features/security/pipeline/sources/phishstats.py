"""PhishStats source — community phishing database (keyless).

Queries the PhishStats API for entries whose registered domain exactly matches
the target's. A match means the domain is a known phishing host.
"""

import logging
from urllib.parse import urlparse

import requests

from .....core.config import HTTP_TIMEOUT_SECONDS
from ..constants import PHISHSTATS_API_URL

logger = logging.getLogger(__name__)

NAME = "PhishStats"


def _registered_domain(url: str) -> str:
    host = urlparse(url).netloc or url
    return host[4:] if host.startswith("www.") else host


def query(url: str) -> dict | None:
    domain = _registered_domain(url)
    resp = requests.get(
        PHISHSTATS_API_URL,
        params={"_where": f"(domain,eq,{domain})", "_size": 5},
        headers={"User-Agent": "ticketguard/1.0"},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    matches = resp.json()
    count = len(matches)
    return {
        "name": NAME,
        "threat": count > 0,
        "match_count": count,
        "detail": (
            f"{count} PhishStats phishing record(s) for {domain}."
            if count
            else f"No PhishStats record for {domain}."
        ),
    }

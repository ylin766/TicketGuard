"""RDAP source — standardized WHOIS registration data (keyless, context).

Looks up the domain's RDAP record and reports its registration date and status.
A very recently registered domain is a weak credibility signal — context for the
agent, not a threat verdict.
"""

import logging
from urllib.parse import urlparse

import requests

from ..http_utils import SLOW_TIMEOUT_LEVELS, fetch_with_retry

from ..constants import RDAP_API_BASE

logger = logging.getLogger(__name__)

NAME = "RDAP"


def _registered_domain(url: str) -> str:
    host = urlparse(url).netloc or url
    return host[4:] if host.startswith("www.") else host


def query(url: str) -> dict | None:
    domain = _registered_domain(url)
    resp = fetch_with_retry(
        "GET",
        f"{RDAP_API_BASE}/{domain}",
        headers={"User-Agent": "ticketguard/1.0"},
        timeout_levels=SLOW_TIMEOUT_LEVELS,
    )
    resp.raise_for_status()
    data = resp.json()

    registered = None
    for event in data.get("events") or []:
        if event.get("eventAction") == "registration":
            registered = event.get("eventDate")
            break
    statuses = data.get("status") or []
    return {
        "name": NAME,
        # Credibility signal, not a threat: context only.
        "threat": None,
        "registered_on": registered,
        "status": statuses,
        "detail": (
            f"Domain registered on {registered}."
            if registered
            else f"RDAP record found for {domain} (no registration date)."
        ),
    }

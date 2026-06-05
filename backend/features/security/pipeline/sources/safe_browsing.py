"""Google Safe Browsing source — Google's malware / social-engineering lists.

Returns ``None`` when ``SAFE_BROWSING_API_KEY`` is unset so the aggregator skips it.
"""

import logging
import os

import requests

from .....core.config import HTTP_TIMEOUT_SECONDS
from ..constants import SAFE_BROWSING_API_KEY_ENV, SAFE_BROWSING_API_URL

logger = logging.getLogger(__name__)

NAME = "SafeBrowsing"

_THREAT_TYPES = [
    "MALWARE",
    "SOCIAL_ENGINEERING",
    "UNWANTED_SOFTWARE",
    "POTENTIALLY_HARMFUL_APPLICATION",
]


def query(url: str) -> dict | None:
    api_key = os.environ.get(SAFE_BROWSING_API_KEY_ENV)
    if not api_key:
        return None

    body = {
        "client": {"clientId": "ticketguard", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes": _THREAT_TYPES,
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": url}],
        },
    }
    resp = requests.post(
        SAFE_BROWSING_API_URL,
        params={"key": api_key},
        json=body,
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    matches = resp.json().get("matches", [])
    threats = sorted({m["threatType"] for m in matches})
    return {
        "name": NAME,
        # Authoritative blacklist: a binary listed/not-listed verdict.
        "kind": "blacklist_verdict",
        "listed": bool(matches),
        "threats": threats,
        "detail": "Listed: " + ", ".join(threats) if threats else "No Safe Browsing match.",
    }

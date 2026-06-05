"""URLhaus (abuse.ch) source — community malware-URL blacklist.

Returns ``None`` when ``URLHAUS_AUTH_KEY`` is unset so the aggregator skips it.
abuse.ch requires an Auth-Key for all API requests.
"""

import logging
import os

import requests

from .....core.config import HTTP_TIMEOUT_SECONDS
from ..constants import URLHAUS_API_URL, URLHAUS_AUTH_KEY_ENV

logger = logging.getLogger(__name__)

NAME = "URLhaus"


def query(url: str) -> dict | None:
    auth_key = os.environ.get(URLHAUS_AUTH_KEY_ENV)
    if not auth_key:
        return None

    resp = requests.post(
        URLHAUS_API_URL,
        headers={"Auth-Key": auth_key, "User-Agent": "ticketguard/1.0"},
        data={"url": url},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    payload = resp.json()
    status = payload.get("query_status")

    if status == "ok":
        threat = payload.get("threat", "listed")
        return {
            "name": NAME,
            # Authoritative blacklist: a binary listed/not-listed verdict.
            "kind": "blacklist_verdict",
            "listed": True,
            "threats": [threat],
            "detail": f"Listed in URLhaus ({threat}).",
        }
    if status == "no_results":
        return {"name": NAME, "kind": "blacklist_verdict", "listed": False,
                "threats": [], "detail": "Not listed in URLhaus."}
    return {"name": NAME, "kind": "blacklist_verdict", "listed": False,
            "threats": [], "detail": f"URLhaus status: {status}."}

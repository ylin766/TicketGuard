"""Wayback Machine source — historical snapshot availability (keyless, context).

Reports whether the Internet Archive has any snapshot of the URL and when the
closest one was taken. A site with no history is a weak credibility signal —
context for the agent, not a threat verdict.
"""

import logging

import requests

from .....core.config import HTTP_TIMEOUT_SECONDS
from ..constants import WAYBACK_AVAILABLE_URL

logger = logging.getLogger(__name__)

NAME = "Wayback"


def query(url: str) -> dict | None:
    resp = requests.get(
        WAYBACK_AVAILABLE_URL,
        params={"url": url},
        headers={"User-Agent": "ticketguard/1.0"},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    closest = (resp.json().get("archived_snapshots") or {}).get("closest") or {}
    timestamp = closest.get("timestamp")
    return {
        "name": NAME,
        # Credibility signal, not a threat: context only.
        "threat": None,
        "has_snapshot": bool(closest),
        "closest_timestamp": timestamp,
        "detail": (
            f"Archived; closest snapshot {timestamp}."
            if closest
            else "No Wayback Machine snapshot found."
        ),
    }

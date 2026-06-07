"""Sucuri SiteCheck source — remote website malware / blacklist scanner.

Public JSON endpoint behind the SiteCheck site; no API key required. Reports
whether the site is blacklisted by any vendor or has malware warnings (a hit
means the hit itself, not a number).

Always runs — there is no key to gate it — so this source has no env var.
"""

import logging

import requests

from ..http_utils import DEFAULT_TIMEOUT_LEVELS, fetch_with_retry

from ..constants import SUCURI_API_URL

logger = logging.getLogger(__name__)

NAME = "Sucuri"


def query(url: str) -> dict | None:
    resp = fetch_with_retry(
        "GET",
        SUCURI_API_URL,
        params={"scan": url},
        headers={"User-Agent": "ticketguard/1.0"},
        timeout_levels=DEFAULT_TIMEOUT_LEVELS,
    )
    resp.raise_for_status()
    data = resp.json()

    blacklists = data.get("blacklists") or []
    warnings = data.get("warnings") or {}
    
    # Ignore operational warnings that are not security threats
    security_warnings = {k: v for k, v in warnings.items() if k not in ("scan_failed", "site_error")}
    
    blacklisted_by = [b.get("vendor", "blacklist") for b in blacklists]
    malware = bool(security_warnings)
    flagged_by = blacklisted_by + (["malware"] if malware else [])
    detail = (
        "Blacklisted/flagged by: " + ", ".join(flagged_by)
        if flagged_by
        else "No Sucuri blacklist or malware warning."
    )
    return {
        "name": NAME,
        "threat": bool(flagged_by),
        "blacklisted_by": blacklisted_by,
        "malware": malware,
        "detail": detail,
    }

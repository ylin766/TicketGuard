"""MetaDefender Cloud (OPSWAT) source — multi-engine URL reputation.

Looks up the URL against MetaDefender's online reputation engines and reports
how many of them detected a threat (an engine-detection count, like VirusTotal).

Returns ``None`` when ``METADEFENDER_API_KEY`` is unset so the aggregator skips it.
"""

import logging
import os
from urllib.parse import quote

import requests

from ..http_utils import DEFAULT_TIMEOUT_LEVELS, fetch_with_retry

from ..constants import METADEFENDER_API_KEY_ENV, METADEFENDER_URL_BASE

logger = logging.getLogger(__name__)

NAME = "MetaDefender"


def query(url: str) -> dict | None:
    api_key = os.environ.get(METADEFENDER_API_KEY_ENV)
    if not api_key:
        return None

    resp = fetch_with_retry(
        "GET",
        f"{METADEFENDER_URL_BASE}/{quote(url, safe='')}",
        headers={"apikey": api_key},
        timeout_levels=DEFAULT_TIMEOUT_LEVELS,
    )
    resp.raise_for_status()
    lookup = resp.json().get("lookup_results", {})
    detected = lookup.get("detected_by", 0)
    total = len(lookup.get("sources", []))
    return {
        "name": NAME,
        "threat": detected > 0,
        "detected_by": detected,
        "total": total,
        "detail": f"{detected} of {total} reputation engines detected a threat.",
    }

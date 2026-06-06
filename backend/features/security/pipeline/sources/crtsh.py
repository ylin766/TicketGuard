"""crt.sh source — Certificate Transparency log lookup (keyless, context).

Reports how many CT-logged certificates exist for the domain and when the
earliest was issued. A brand-new domain with no certificate history is a weak
credibility signal — context for the agent, not a threat verdict.
"""

import logging
from urllib.parse import urlparse

import requests

from ..http_utils import SLOW_TIMEOUT_LEVELS, fetch_with_retry

from ..constants import CRTSH_API_URL

logger = logging.getLogger(__name__)

NAME = "crt.sh"


def _registered_domain(url: str) -> str:
    host = urlparse(url).netloc or url
    return host[4:] if host.startswith("www.") else host


def query(url: str) -> dict | None:
    domain = _registered_domain(url)
    resp = fetch_with_retry(
        "GET",
        CRTSH_API_URL,
        params={"q": domain, "output": "json"},
        headers={"User-Agent": "ticketguard/1.0"},
        timeout_levels=SLOW_TIMEOUT_LEVELS,
    )
    resp.raise_for_status()
    certs = resp.json() if resp.text.strip() else []
    earliest = min((c.get("not_before", "") for c in certs if c.get("not_before")), default=None)
    return {
        "name": NAME,
        # Credibility signal, not a threat: context only.
        "threat": None,
        "certificate_count": len(certs),
        "earliest_certificate": earliest,
        "detail": (
            f"{len(certs)} certificate(s) in CT logs, earliest {earliest}."
            if certs
            else f"No certificates found in CT logs for {domain}."
        ),
    }

"""IP geolocation source — resolve the domain, then geo-locate it (keyless, context).

Resolves the domain's A record via DNS-over-HTTPS (dns.google), then looks up
the IP's country / ASN / ISP. Pure context for the agent (where is this hosted),
not a threat verdict.
"""

import logging
from urllib.parse import urlparse

import requests

from .....core.config import HTTP_TIMEOUT_SECONDS
from ..constants import DNS_RESOLVE_URL, IPGEO_API_BASE

logger = logging.getLogger(__name__)

NAME = "IPGeo"


def _host(url: str) -> str:
    host = urlparse(url).netloc or url
    return host[4:] if host.startswith("www.") else host


def _resolve(domain: str) -> str | None:
    resp = requests.get(
        DNS_RESOLVE_URL,
        params={"name": domain, "type": "A"},
        headers={"User-Agent": "ticketguard/1.0"},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    for answer in resp.json().get("Answer") or []:
        if answer.get("type") == 1:  # A record
            return answer.get("data")
    return None


def query(url: str) -> dict | None:
    domain = _host(url)
    ip = _resolve(domain)
    if not ip:
        return {
            "name": NAME,
            "threat": None,
            "ip": None,
            "detail": f"{domain} did not resolve to an IPv4 address.",
        }

    geo = requests.get(
        f"{IPGEO_API_BASE}/{ip}",
        headers={"User-Agent": "ticketguard/1.0"},
        timeout=HTTP_TIMEOUT_SECONDS,
    ).json()
    country = geo.get("countryName")
    isp = (geo.get("asn") or {}).get("isp") if isinstance(geo.get("asn"), dict) else geo.get("isp")
    return {
        "name": NAME,
        # Hosting context, not a threat: context only.
        "threat": None,
        "ip": ip,
        "country": country,
        "isp": isp,
        "detail": f"{domain} resolves to {ip} ({country or 'unknown country'}).",
    }

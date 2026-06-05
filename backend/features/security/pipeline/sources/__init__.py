"""Threat-intel sources for the aggregator.

Each module exposes ``query(url) -> dict | None``:
  * ``None``  -> the source's API key is not configured, so it is skipped.
  * ``dict``  -> the source's native report; it always includes ``name``,
                 ``detail``, and ``threat`` (True / False for a threat verdict,
                 or None for a non-threat intelligence signal).

``ALL_SOURCES`` lists the modules the aggregator polls (in parallel).
"""

from . import (
    checkphish,
    crtsh,
    ipgeo,
    metadefender,
    openphish,
    phishstats,
    rdap,
    safe_browsing,
    sucuri,
    tranco,
    urlhaus,
    virustotal,
    wayback,
)

ALL_SOURCES = (
    # Threat verdicts (threat = True/False).
    virustotal,
    safe_browsing,
    urlhaus,
    checkphish,
    metadefender,
    sucuri,
    openphish,
    phishstats,
    # Intelligence context (threat = None).
    tranco,
    crtsh,
    wayback,
    rdap,
    ipgeo,
)

__all__ = ["ALL_SOURCES"]

"""Threat-intel sources for the aggregator.

Each module exposes ``query(url) -> dict | None``:
  * ``None``  -> the source's API key is not configured, so it is skipped.
  * ``dict``  -> {"name": str, "malicious": bool, "detail": str}.

``ALL_SOURCES`` lists the modules the aggregator polls (in parallel).
"""

from . import safe_browsing, urlhaus, virustotal

ALL_SOURCES = (virustotal, safe_browsing, urlhaus)

__all__ = ["ALL_SOURCES"]

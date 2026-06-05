"""SpiderFoot detector — deterministic, no LLM.

Starts an OSINT scan against the target URL on a self-hosted SpiderFoot
instance, polls until the scan finishes, then counts threat-signal events
(MALICIOUS_*, BLACKLISTED_*) and normalizes them into a 0-100 risk score.

Pure function: takes a URL, returns a normalized dict. No session state.
"""

import logging
import os
import time
from urllib.parse import urlparse

import requests

from ....core.config import HTTP_TIMEOUT_SECONDS
from .constants import (
    DETECTOR_POLL_INTERVAL_SECONDS,
    SPIDERFOOT_DEFAULT_URL,
    SPIDERFOOT_MALICIOUS_PREFIXES,
    SPIDERFOOT_MAX_WAIT_SECONDS,
    SPIDERFOOT_URL_ENV,
    SPIDERFOOT_USECASE,
)

logger = logging.getLogger(__name__)

_FINISHED_STATES = frozenset({"FINISHED", "ABORTED", "ERROR-FAILED"})
# Each distinct malicious event adds this much risk, capped at 100.
_RISK_PER_HIT = 30


def _base_url() -> str:
    return os.environ.get(SPIDERFOOT_URL_ENV, SPIDERFOOT_DEFAULT_URL).rstrip("/")


def _start_scan(base: str, target: str) -> None:
    """Kick off a SpiderFoot scan for the target."""
    requests.post(
        f"{base}/startscan",
        data={
            "scanname": f"ticketguard-{urlparse(target).netloc or target}",
            "scantarget": target,
            "usecase": SPIDERFOOT_USECASE,
            "modulelist": "",
            "typelist": "",
        },
        timeout=HTTP_TIMEOUT_SECONDS,
    )


def _latest_scan_id(base: str) -> str | None:
    scans = requests.get(f"{base}/scanlist", timeout=HTTP_TIMEOUT_SECONDS).json()
    return scans[0][0] if scans else None


def _scan_state(base: str, scan_id: str) -> str:
    status = requests.get(
        f"{base}/scanstatus", params={"id": scan_id}, timeout=HTTP_TIMEOUT_SECONDS
    ).json()
    return status[0][2]


def _count_malicious(base: str, scan_id: str) -> list[str]:
    """Return the data values of all malicious / blacklisted events."""
    results = requests.get(
        f"{base}/scanresults", params={"id": scan_id}, timeout=HTTP_TIMEOUT_SECONDS
    ).json()
    hits: list[str] = []
    for item in results:
        event_type = str(item[0])
        if event_type.startswith(SPIDERFOOT_MALICIOUS_PREFIXES):
            hits.append(str(item[2])[:120])
    return hits


def run_spiderfoot(url: str) -> dict:
    """Scan a URL with SpiderFoot and return a normalized risk score.

    Args:
        url: The full ticket-listing URL to scan.

    Returns:
        dict with keys: status ("ok" | "unavailable" | "error"), risk_score,
        flags, detail.
    """
    try:
        if not os.environ.get(SPIDERFOOT_URL_ENV):
            return {"status": "unavailable", "risk_score": None,
                    "flags": [], "detail": "SpiderFoot not configured."}

        base = _base_url()
        _start_scan(base, url)
        scan_id = _latest_scan_id(base)
        if not scan_id:
            raise ValueError("SpiderFoot did not register a scan.")

        deadline = time.monotonic() + SPIDERFOOT_MAX_WAIT_SECONDS
        while time.monotonic() < deadline:
            if _scan_state(base, scan_id) in _FINISHED_STATES:
                break
            time.sleep(DETECTOR_POLL_INTERVAL_SECONDS)

        hits = _count_malicious(base, scan_id)
        risk = min(100, len(hits) * _RISK_PER_HIT)
        detail = f"SpiderFoot found {len(hits)} malicious/blacklisted signal(s)."
        return {"status": "ok", "risk_score": risk, "flags": hits[:5], "detail": detail}
    except Exception as exc:  # noqa: BLE001 - detector must always return a dict
        logger.error("SpiderFoot check failed: %s", exc)
        return {"status": "error", "risk_score": None, "flags": [], "detail": str(exc)}

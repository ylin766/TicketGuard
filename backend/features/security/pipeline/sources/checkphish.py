"""CheckPhish (Bolster) source — AI phishing/scam URL classifier.

Submits the URL for a scan, polls until done, then reports the disposition
(clean / phish / scam / suspicious / ...). A non-clean disposition is a threat.

Returns ``None`` when ``CHECKPHISH_API_KEY`` is unset so the aggregator skips it.
"""

import logging
import os
import time

import requests

from .....core.config import HTTP_TIMEOUT_SECONDS
from ..constants import (
    CHECKPHISH_API_KEY_ENV,
    CHECKPHISH_SCAN_URL,
    CHECKPHISH_STATUS_URL,
    DETECTOR_POLL_INTERVAL_SECONDS,
    THREATINTEL_MAX_WAIT_SECONDS,
)

logger = logging.getLogger(__name__)

NAME = "CheckPhish"


def _scan_and_wait(api_key: str, url: str) -> str:
    """Submit a scan, poll until done, and return the disposition."""
    submit = requests.post(
        CHECKPHISH_SCAN_URL,
        json={"apiKey": api_key, "urlInfo": {"url": url}, "scanType": "quick"},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    submit.raise_for_status()
    job_id = submit.json()["jobID"]

    deadline = time.monotonic() + THREATINTEL_MAX_WAIT_SECONDS
    while time.monotonic() < deadline:
        report = requests.post(
            CHECKPHISH_STATUS_URL,
            json={"apiKey": api_key, "jobID": job_id, "insights": False},
            timeout=HTTP_TIMEOUT_SECONDS,
        ).json()
        if report.get("status") == "DONE":
            return report.get("disposition", "unknown")
        time.sleep(DETECTOR_POLL_INTERVAL_SECONDS)
    raise TimeoutError("CheckPhish scan did not complete in time.")


def query(url: str) -> dict | None:
    api_key = os.environ.get(CHECKPHISH_API_KEY_ENV)
    if not api_key:
        return None

    disposition = _scan_and_wait(api_key, url)
    return {
        "name": NAME,
        "threat": disposition not in ("clean", "unknown"),
        "disposition": disposition,
        "detail": f"CheckPhish disposition: {disposition}.",
    }

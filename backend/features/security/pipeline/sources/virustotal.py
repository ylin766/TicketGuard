"""VirusTotal source — aggregates 70+ engines (incl. many phishing feeds).

Returns ``None`` when ``VIRUSTOTAL_API_KEY`` is unset so the aggregator skips it.
"""

import base64
import logging
import os
import time

import requests

from .....core.config import HTTP_TIMEOUT_SECONDS
from ..constants import (
    DETECTOR_POLL_INTERVAL_SECONDS,
    THREATINTEL_MAX_WAIT_SECONDS,
    VIRUSTOTAL_API_BASE,
    VIRUSTOTAL_API_KEY_ENV,
)

logger = logging.getLogger(__name__)

NAME = "VirusTotal"


def _url_id(url: str) -> str:
    """VirusTotal's URL identifier: base64url(url) without padding."""
    return base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")


def _submit_and_wait(url: str, headers: dict) -> dict:
    """Submit a not-yet-seen URL, poll until the analysis completes."""
    submit = requests.post(
        f"{VIRUSTOTAL_API_BASE}/urls",
        headers=headers,
        data={"url": url},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    submit.raise_for_status()
    analysis_id = submit.json()["data"]["id"]

    deadline = time.monotonic() + THREATINTEL_MAX_WAIT_SECONDS
    while time.monotonic() < deadline:
        report = requests.get(
            f"{VIRUSTOTAL_API_BASE}/analyses/{analysis_id}",
            headers=headers,
            timeout=HTTP_TIMEOUT_SECONDS,
        ).json()
        attributes = report["data"]["attributes"]
        if attributes["status"] == "completed":
            return attributes["stats"]
        time.sleep(DETECTOR_POLL_INTERVAL_SECONDS)
    raise TimeoutError("VirusTotal analysis did not complete in time.")


def query(url: str) -> dict | None:
    api_key = os.environ.get(VIRUSTOTAL_API_KEY_ENV)
    if not api_key:
        return None

    headers = {"x-apikey": api_key}
    resp = requests.get(
        f"{VIRUSTOTAL_API_BASE}/urls/{_url_id(url)}",
        headers=headers,
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    if resp.status_code == 404:
        stats = _submit_and_wait(url, headers)
    else:
        resp.raise_for_status()
        stats = resp.json()["data"]["attributes"]["last_analysis_stats"]

    malicious = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)
    total = sum(stats.values())
    return {
        "name": NAME,
        # Graded source: a reputation score from many engine votes, not a yes/no.
        "kind": "reputation_score",
        "malicious": malicious,
        "suspicious": suspicious,
        "total": total,
        "detail": f"{malicious} malicious / {suspicious} suspicious of {total} engines.",
    }

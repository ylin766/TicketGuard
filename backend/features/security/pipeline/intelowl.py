"""IntelOwl detector — deterministic, no LLM.

Submits the target URL to a self-hosted IntelOwl instance, runs the free
analyzer playbook (VirusTotal, Phishtank, URLhaus, Google Safe Browsing, ...),
then normalizes the many analyzer verdicts into a single 0-100 risk score.

Pure function: takes a URL, returns a normalized dict. No session state.
"""

import logging
import os
import time
from typing import Any

from .constants import (
    DETECTOR_POLL_INTERVAL_SECONDS,
    INTELOWL_MAX_WAIT_SECONDS,
    INTELOWL_PLAYBOOK,
    INTELOWL_TOKEN_ENV,
    INTELOWL_URL_ENV,
    RISK_FLOOR_MULTI_HIT,
    RISK_FLOOR_SINGLE_HIT,
)

logger = logging.getLogger(__name__)

# IntelOwl job statuses that mean the job has stopped running.
_TERMINAL_STATUSES = frozenset(
    {"reported_without_fails", "reported_with_fails", "failed", "killed"}
)


def _get_client() -> Any | None:
    """Build an IntelOwl client from env vars, or None if not configured."""
    url = os.environ.get(INTELOWL_URL_ENV)
    token = os.environ.get(INTELOWL_TOKEN_ENV)
    if not url or not token:
        return None
    from pyintelowl import IntelOwl  # lazy import; optional dependency

    return IntelOwl(token, url, certificate=False)


def _report_is_malicious(report: Any) -> bool:
    """Recursively decide whether one analyzer report signals maliciousness."""
    if isinstance(report, dict):
        for key, value in report.items():
            key_lower = str(key).lower()
            if key_lower in ("malicious", "is_malicious", "phishing") and value in (True, 1):
                return True
            if (
                key_lower == "last_analysis_stats"
                and isinstance(value, dict)
                and value.get("malicious", 0) > 0
            ):
                return True
            if _report_is_malicious(value):
                return True
    elif isinstance(report, list):
        return any(_report_is_malicious(item) for item in report)
    return False


def _normalize(analyzer_reports: list[dict]) -> dict:
    """Collapse per-analyzer reports into a 0-100 risk score with flags."""
    evaluated = [r for r in analyzer_reports if r.get("status") == "SUCCESS"]
    malicious = [r for r in evaluated if _report_is_malicious(r.get("report"))]

    if not evaluated:
        return {"status": "ok", "risk_score": 0, "flags": [], "detail": "No analyzer returned a verdict."}

    ratio_risk = round(100 * len(malicious) / len(evaluated))
    if len(malicious) >= 2:
        risk = max(ratio_risk, RISK_FLOOR_MULTI_HIT)
    elif len(malicious) == 1:
        risk = max(ratio_risk, RISK_FLOOR_SINGLE_HIT)
    else:
        risk = ratio_risk

    flags = [r.get("name", "analyzer") for r in malicious]
    detail = f"{len(malicious)}/{len(evaluated)} IntelOwl analyzers flagged the URL."
    return {"status": "ok", "risk_score": risk, "flags": flags, "detail": detail}


def run_intelowl(url: str) -> dict:
    """Analyze a URL with IntelOwl and return a normalized risk score.

    Args:
        url: The full ticket-listing URL to analyze.

    Returns:
        dict with keys: status ("ok" | "unavailable" | "error"), risk_score,
        flags, detail.
    """
    try:
        client = _get_client()
        if client is None:
            return {"status": "unavailable", "risk_score": None,
                    "flags": [], "detail": "IntelOwl not configured."}

        response = client.send_observable_analysis_playbook_request(
            observable_name=url,
            observable_classification="url",
            playbook_requested=INTELOWL_PLAYBOOK,
        )
        job_id = response.get("job_id") or response.get("results", [{}])[0].get("job_id")
        if not job_id:
            raise ValueError("IntelOwl did not return a job id.")

        deadline = time.monotonic() + INTELOWL_MAX_WAIT_SECONDS
        job: dict = {}
        while time.monotonic() < deadline:
            job = client.ask_analysis_result(job_id)
            if job.get("status") in _TERMINAL_STATUSES:
                break
            time.sleep(DETECTOR_POLL_INTERVAL_SECONDS)

        return _normalize(job.get("analyzer_reports", []))
    except Exception as exc:  # noqa: BLE001 - detector must always return a dict
        logger.error("IntelOwl check failed: %s", exc)
        return {"status": "error", "risk_score": None, "flags": [], "detail": str(exc)}

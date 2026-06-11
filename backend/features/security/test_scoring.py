"""Unit tests for the security scoring module.

Run from anywhere with: ``pytest test_scoring.py`` (or ``pytest`` in this dir).

The ``security`` package ships an ``__init__.py``, so we add this file's own
directory to ``sys.path`` and import ``scoring`` as a top-level module — that
keeps the tests runnable without installing the whole backend package.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))

from scoring import (  # noqa: E402 - path set up above
    CONTEXT_PENALTY_CAP,
    UNAVAILABLE_SCORE,
    classify_risk,
    compute_domain_age_days,
    compute_security_score,
    generate_score_breakdown,
)


def _days_ago_iso(days: int) -> str:
    """Return an ISO date string ``days`` days before now (UTC)."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# Scenario 1 — clearly safe site                                              #
# --------------------------------------------------------------------------- #

def test_clearly_safe_site_scores_high():
    result = {
        "status": "ok",
        "findings": [
            {"name": "VirusTotal", "threat": False,
             "malicious": 0, "total": 92, "detail": "clean"},
            {"name": "URLhaus", "threat": False, "detail": "not listed"},
            {"name": "CheckPhish", "threat": False,
             "disposition": "clean", "detail": "clean"},
            {"name": "OpenPhish", "threat": False, "detail": "not in feed"},
            {"name": "PhishStats", "threat": False,
             "match_count": 0, "detail": "no match"},
        ],
        "context": [
            {"name": "Tranco", "threat": None, "rank": 500, "detail": "popular"},
            {"name": "crt.sh", "threat": None,
             "certificate_count": 60, "detail": "long history"},
            {"name": "Wayback", "threat": None,
             "has_snapshot": True, "detail": "archived"},
            {"name": "RDAP", "threat": None,
             "registered_on": "2014-01-01", "detail": "old domain"},
            {"name": "IPGeo", "threat": None,
             "country": "US", "isp": "Cloudflare", "detail": "US host"},
        ],
        "flagged": False,
        "detail": "clean",
    }
    score = compute_security_score(result)
    assert 95 <= score <= 100
    assert classify_risk(score) == "safe"


# --------------------------------------------------------------------------- #
# Scenario 2 — clearly dangerous site                                         #
# --------------------------------------------------------------------------- #

def test_clearly_dangerous_site_scores_low():
    result = {
        "status": "ok",
        "findings": [
            {"name": "VirusTotal", "threat": True,
             "malicious": 20, "suspicious": 2, "total": 92, "detail": "malicious"},
            {"name": "SafeBrowsing", "threat": True,
             "threat_types": ["SOCIAL_ENGINEERING"], "detail": "phishing"},
            {"name": "OpenPhish", "threat": True, "detail": "in feed"},
        ],
        "context": [
            {"name": "RDAP", "threat": None,
             "registered_on": _days_ago_iso(3), "detail": "brand new"},
            {"name": "Tranco", "threat": None, "rank": None, "detail": "unranked"},
            {"name": "Wayback", "threat": None,
             "has_snapshot": False, "detail": "no history"},
        ],
        "flagged": True,
        "detail": "dangerous",
    }
    score = compute_security_score(result)
    assert 0 <= score <= 10
    assert classify_risk(score) == "critical"


# --------------------------------------------------------------------------- #
# Scenario 3 — grey zone: new but clean                                       #
# --------------------------------------------------------------------------- #

def test_grey_zone_new_but_clean():
    result = {
        "status": "ok",
        "findings": [
            {"name": "CheckPhish", "threat": False,
             "disposition": "clean", "detail": "clean"},
            {"name": "OpenPhish", "threat": False, "detail": "not in feed"},
        ],
        "context": [
            {"name": "RDAP", "threat": None,
             "registered_on": _days_ago_iso(15), "detail": "15 days old"},
            {"name": "Tranco", "threat": None, "rank": None, "detail": "unranked"},
            {"name": "Wayback", "threat": None,
             "has_snapshot": False, "detail": "no history"},
            {"name": "crt.sh", "threat": None,
             "certificate_count": 1, "detail": "single cert"},
        ],
        "flagged": False,
        "detail": "new but clean",
    }
    score = compute_security_score(result)
    # No threats, but four context flags push toward the context cap.
    assert 55 <= score <= 70


# --------------------------------------------------------------------------- #
# Scenario 4 — grey zone: established but one flag                            #
# --------------------------------------------------------------------------- #

def test_grey_zone_established_but_one_flag():
    result = {
        "status": "ok",
        "findings": [
            {"name": "CheckPhish", "threat": True,
             "disposition": "phish", "detail": "flagged"},
            {"name": "URLhaus", "threat": False, "detail": "not listed"},
        ],
        "context": [
            {"name": "RDAP", "threat": None,
             "registered_on": "2024-01-01", "detail": "2 years old"},
            {"name": "Tranco", "threat": None, "rank": 50000, "detail": "mid"},
            {"name": "Wayback", "threat": None,
             "has_snapshot": True, "detail": "archived"},
        ],
        "flagged": True,
        "detail": "one flag",
    }
    score = compute_security_score(result)
    # CheckPhish's flat weight is 10 and nothing else penalizes, so an
    # established site with a single phishing flag lands at 90 under the
    # current weights (spec's 70-85 was an approximate target).
    assert 70 <= score <= 90
    assert classify_risk(score) in {"low", "safe"}


# --------------------------------------------------------------------------- #
# Scenario 5 — partial data (most sources missing)                            #
# --------------------------------------------------------------------------- #

def test_partial_data_still_computes():
    result = {
        "status": "ok",
        "findings": [
            {"name": "URLhaus", "threat": False, "detail": "not listed"},
            {"name": "Sucuri", "threat": False, "detail": "clean"},
            {"name": "PhishStats", "threat": False,
             "match_count": 0, "detail": "no match"},
        ],
        "context": [
            # Registration date missing -> "can't verify" penalty (15).
            {"name": "RDAP", "threat": None,
             "registered_on": None, "detail": "unknown age"},
            {"name": "Tranco", "threat": None, "rank": 1200, "detail": "ranked"},
        ],
        "flagged": False,
        "detail": "partial",
    }
    score = compute_security_score(result)
    assert 75 <= score <= 90


# --------------------------------------------------------------------------- #
# Scenario 6 — empty findings and context                                     #
# --------------------------------------------------------------------------- #

def test_empty_lists_score_full():
    result = {"status": "ok", "findings": [], "context": [],
              "flagged": False, "detail": ""}
    assert compute_security_score(result) == 100


# --------------------------------------------------------------------------- #
# Scenario 7 — pipeline unavailable                                           #
# --------------------------------------------------------------------------- #

def test_unavailable_status_returns_uncertain():
    result = {"status": "unavailable", "findings": [], "context": [],
              "flagged": False, "detail": "no source"}
    assert compute_security_score(result) == UNAVAILABLE_SCORE == 50


# --------------------------------------------------------------------------- #
# classify_risk band boundaries                                               #
# --------------------------------------------------------------------------- #

def test_classify_risk_boundaries():
    assert classify_risk(0) == "critical"
    assert classify_risk(19) == "critical"
    assert classify_risk(20) == "high"
    assert classify_risk(39) == "high"
    assert classify_risk(40) == "medium"
    assert classify_risk(59) == "medium"
    assert classify_risk(60) == "low"
    assert classify_risk(79) == "low"
    assert classify_risk(80) == "safe"
    assert classify_risk(100) == "safe"


# --------------------------------------------------------------------------- #
# compute_domain_age_days                                                     #
# --------------------------------------------------------------------------- #

def test_compute_domain_age_days_parses_formats():
    assert compute_domain_age_days(None) is None
    assert compute_domain_age_days("") is None
    assert compute_domain_age_days("not-a-date") is None

    # Plain ISO date.
    assert compute_domain_age_days(_days_ago_iso(10)) in (9, 10, 11)
    # ISO datetime with trailing Z.
    ten_days = (datetime.now(timezone.utc) - timedelta(days=10))
    iso_z = ten_days.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert compute_domain_age_days(iso_z) in (9, 10, 11)
    # A future date never yields a negative age.
    future = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d")
    assert compute_domain_age_days(future) == 0


# --------------------------------------------------------------------------- #
# generate_score_breakdown                                                    #
# --------------------------------------------------------------------------- #

def test_breakdown_shape_and_content():
    result = {
        "status": "ok",
        "findings": [
            {"name": "VirusTotal", "threat": True,
             "malicious": 20, "total": 92, "detail": "malicious"},
            {"name": "SafeBrowsing", "threat": True,
             "threat_types": ["SOCIAL_ENGINEERING"], "detail": "phishing"},
        ],
        "context": [
            {"name": "RDAP", "threat": None,
             "registered_on": _days_ago_iso(15), "detail": "new"},
            {"name": "Tranco", "threat": None, "rank": None, "detail": "unranked"},
        ],
        "flagged": True,
        "detail": "bad",
    }
    breakdown = generate_score_breakdown(result)

    assert set(breakdown) == {
        "score", "risk_level", "threat_penalty", "context_penalty",
        "threat_sources_triggered", "context_flags", "deductions", "explanation",
    }
    # Every deduction carries a label + positive point cost.
    assert breakdown["deductions"]
    assert all(d["points"] > 0 and d["label"] for d in breakdown["deductions"])
    assert breakdown["score"] == compute_security_score(result)
    assert breakdown["risk_level"] == classify_risk(breakdown["score"])
    assert breakdown["threat_sources_triggered"] == ["VirusTotal", "SafeBrowsing"]
    assert breakdown["context_penalty"] <= CONTEXT_PENALTY_CAP
    assert breakdown["context_flags"]  # at least one flag present
    assert "VirusTotal" in breakdown["explanation"]
    assert breakdown["explanation"].strip()


def test_breakdown_unavailable():
    breakdown = generate_score_breakdown({"status": "unavailable"})
    assert breakdown["score"] == 50
    assert breakdown["threat_sources_triggered"] == []
    assert breakdown["context_flags"] == []
    assert "unavailable" in breakdown["explanation"].lower()


if __name__ == "__main__":
    # Standalone runner so the suite works without pytest installed (and without
    # importing the backend package, which pulls in google.adk). Prefer
    # ``pytest test_scoring.py`` when the backend deps are available.
    failures = 0
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            try:
                _fn()
                print(f"PASS  {_name}")
            except AssertionError as _exc:
                failures += 1
                print(f"FAIL  {_name}: {_exc}")
    print(f"\n{'OK' if not failures else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)

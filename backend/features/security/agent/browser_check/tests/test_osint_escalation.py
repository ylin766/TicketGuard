"""Tests for the OSINT escalation bridge.

These exercise the *decision* parts of the escalation — when to trigger, how to
parse the OSINT trust rating, and how the rating folds into the browser risk —
with hand-built results. They never touch the network or ADK: ``_run_osint_agent``
(the only I/O) is not called here.
"""

from backend.features.security.agent.browser_check.osint import osint_escalation as E
from backend.features.security.agent.browser_check.schemas import (
    BrowserSecurityResult,
    ClaimExtraction,
    OsintVerdict,
    TrustCheck,
)


def _result(
    *,
    trusted: bool = False,
    matches=None,
    platform: str = None,
    domain: str = "weirdtix.xyz",
    score: int = 10,
    level: str = "low",
) -> BrowserSecurityResult:
    return BrowserSecurityResult(
        input_url="http://example.test",
        risk_level=level,
        risk_score=score,
        verdict="likely_safe_browser_context",
        summary="",
        claim=ClaimExtraction(claimed_platform=platform),
        trust_check=TrustCheck(
            is_trusted_marketplace_domain=trusted,
            domain_matches_claimed_platform=matches,
            current_registered_domain=domain,
        ),
    )


# --------------------------------------------------------------------------- #
# should_escalate                                                             #
# --------------------------------------------------------------------------- #

def test_escalates_on_unknown_brand_untrusted_domain():
    assert E.should_escalate(_result(trusted=False, matches=None)) is True


def test_escalates_on_untrusted_self_declared_domain():
    # viagogo-style: untrusted, unknown brand that self-matches its own domain
    # (matches=True) must STILL escalate — the rules can't vouch for it.
    assert E.should_escalate(_result(matches=True, platform="viagogo")) is True


def test_no_escalate_on_trusted_domain():
    # Whitelisted/trusted marketplaces skip OSINT regardless of brand.
    assert E.should_escalate(_result(trusted=True, matches=None)) is False
    assert E.should_escalate(_result(trusted=True, platform="StubHub")) is False


def test_escalates_on_brand_impersonation():
    # A recognized brand claimed on an UNtrusted domain (impersonation) is also
    # non-whitelisted, so it still gets a reputation check.
    assert E.should_escalate(_result(matches=False, platform="Ticketmaster")) is True


def test_no_escalate_without_domain():
    assert E.should_escalate(_result(domain=None)) is False


# --------------------------------------------------------------------------- #
# _parse_trust_rating                                                         #
# --------------------------------------------------------------------------- #

def test_parse_rating_from_score_label():
    assert E._parse_trust_rating("Trust Rating (0-100)\n- Score: 23\nbasis") == 23


def test_parse_rating_from_fraction():
    assert E._parse_trust_rating("overall this lands around 78/100 trust") == 78


def test_parse_rating_none_when_absent():
    assert E._parse_trust_rating("no numeric verdict here") is None


def test_parse_rating_ignores_out_of_range():
    assert E._parse_trust_rating("Score: 250") is None


# --------------------------------------------------------------------------- #
# _fold_into_risk                                                             #
# --------------------------------------------------------------------------- #

def test_bad_reputation_raises_risk():
    r = _result(score=10, level="low")
    E._fold_into_risk(r, OsintVerdict(triggered=True, trust_rating=20))
    assert r.risk_score == 80
    assert r.risk_level == "high"
    assert r.verdict == "high_risk_likely_ticket_scam"


def test_clean_reputation_never_downgrades():
    r = _result(score=70, level="high")
    E._fold_into_risk(r, OsintVerdict(triggered=True, trust_rating=90))
    assert r.risk_score == 70
    assert r.risk_level == "high"


def test_missing_rating_records_caution_evidence():
    r = _result()
    before = len(r.evidence)
    E._fold_into_risk(r, OsintVerdict(triggered=True, trust_rating=None))
    assert len(r.evidence) == before + 1


def test_error_rating_records_failure_evidence():
    r = _result()
    E._fold_into_risk(r, OsintVerdict(triggered=True, trust_rating=None, error="boom"))
    assert any("could not complete" in e for e in r.evidence)

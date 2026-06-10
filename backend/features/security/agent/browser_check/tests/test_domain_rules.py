"""Tests for the deterministic trust + scoring layer.

These exercise the *decision* layer with hand-built snapshots / claim / sensitive
objects (i.e. mocked LLM outputs), so they run without a browser or Gemini. They
cover the six scenarios from the task plan plus the click safety guard and the
JSON extraction helper.
"""

from backend.features.security.agent.browser_check.rules.domain_rules import (
    classify_risk,
    detect_off_platform_payment,
    detect_suspicious_redirect,
    evaluate_trust_and_score,
    platform_matches_domain,
    registered_domain,
)
from backend.features.security.agent.browser_check.llm.gemini_client import extract_json
from backend.features.security.agent.browser_check.schemas import (
    BrowserSnapshot,
    ClaimExtraction,
    SensitiveActionDetection,
)


# --------------------------------------------------------------------------- #
# Fixtures (helpers to build mocked observations)                             #
# --------------------------------------------------------------------------- #

def _snap(url: str, *, body: str = "", title: str = "", step: int = 0) -> BrowserSnapshot:
    return BrowserSnapshot(
        step=step,
        url=url,
        registered_domain=registered_domain(url),
        title=title,
        body_text=body,
    )


def _evaluate(url, snaps, claim, sensitive, **kw):
    return evaluate_trust_and_score(
        input_url=url, snapshots=snaps, claim=claim, sensitive=sensitive, **kw
    )


# --------------------------------------------------------------------------- #
# Domain helpers                                                              #
# --------------------------------------------------------------------------- #

def test_registered_domain_extracts_etld_plus_one():
    assert registered_domain("https://www.ticketmaster.com/event/123") == "ticketmaster.com"
    assert registered_domain("https://buy.tickets.ticketmaster.com/x") == "ticketmaster.com"
    assert registered_domain("not a url") is None


def test_platform_matches_domain():
    assert platform_matches_domain("Ticketmaster", "ticketmaster.com") is True
    assert platform_matches_domain("Ticketmaster", "ticketmaster-secure-transfer.shop") is False
    # Unknown brand → can't assert a mismatch.
    assert platform_matches_domain("Some Random Brand", "whatever.com") is None
    # Live Nation legitimately resolves through Ticketmaster.
    assert platform_matches_domain("Live Nation", "ticketmaster.com") is True


# --------------------------------------------------------------------------- #
# Plan scenario 1: legit event listing                                        #
# --------------------------------------------------------------------------- #

def test_case1_legit_event_listing_is_low():
    url = "https://www.ticketmaster.com/event/world-cup"
    snaps = [_snap(url, body="World Cup tickets", title="Ticketmaster")]
    claim = ClaimExtraction(
        claimed_platform="Ticketmaster", claimed_domain="ticketmaster.com",
        page_state="event_listing", confidence="high",
    )
    sensitive = SensitiveActionDetection(is_sensitive_action_page=False,
                                         page_state="event_listing",
                                         action_types=["none"])
    trust, level, score, verdict, *_ = _evaluate(url, snaps, claim, sensitive)
    assert trust.is_trusted_marketplace_domain is True
    assert level == "low"
    assert verdict == "likely_safe_browser_context"


# --------------------------------------------------------------------------- #
# Plan scenario 2: quantity modal                                             #
# --------------------------------------------------------------------------- #

def test_case2_quantity_modal_not_high():
    url = "https://seatgeek.com/event/abc"
    snaps = [_snap(url, body="How many tickets?")]
    claim = ClaimExtraction(claimed_platform="SeatGeek", page_state="quantity_modal")
    sensitive = SensitiveActionDetection(page_state="quantity_modal", action_types=["none"])
    _, level, score, *_ = _evaluate(url, snaps, claim, sensitive)
    assert level in ("low", "medium")
    assert level != "high"


# --------------------------------------------------------------------------- #
# Plan scenario 3: legit in-platform payment                                  #
# --------------------------------------------------------------------------- #

def test_case3_inside_platform_payment_not_high():
    url = "https://www.ticketmaster.com/checkout"
    snaps = [_snap(url, body="Pay with card or PayPal")]
    claim = ClaimExtraction(claimed_platform="Ticketmaster", page_state="payment_required")
    sensitive = SensitiveActionDetection(
        is_sensitive_action_page=True, page_state="payment_required",
        action_types=["payment"], payment_context="inside_platform",
    )
    trust, level, score, *_ = _evaluate(url, snaps, claim, sensitive)
    assert trust.is_trusted_marketplace_domain is True
    assert level != "high"  # sensitive action inside a trusted platform is not a scam


# --------------------------------------------------------------------------- #
# Plan scenario 4: spoofed brand/domain mismatch                              #
# --------------------------------------------------------------------------- #

def test_case4_brand_domain_mismatch_with_login_is_high():
    url = "https://ticketmaster-secure-transfer.shop/login"
    snaps = [_snap(url, body="Sign in to claim your Ticketmaster tickets")]
    claim = ClaimExtraction(claimed_platform="Ticketmaster", page_state="login_required")
    sensitive = SensitiveActionDetection(
        is_sensitive_action_page=True, page_state="login_required",
        action_types=["login", "password"],
    )
    trust, level, score, verdict, *_ = _evaluate(url, snaps, claim, sensitive)
    assert trust.domain_matches_claimed_platform is False
    assert level == "high"
    assert verdict == "high_risk_likely_ticket_scam"


# --------------------------------------------------------------------------- #
# Plan scenario 5: off-platform payment                                       #
# --------------------------------------------------------------------------- #

def test_case5_off_platform_payment_is_high():
    url = "https://cheap-tix-deals.shop/buy"
    snaps = [_snap(url, body="Pay via Zelle or Venmo, or DM seller on WhatsApp")]
    claim = ClaimExtraction(claimed_platform="StubHub", page_state="off_platform_payment")
    sensitive = SensitiveActionDetection(
        is_sensitive_action_page=True, page_state="off_platform_payment",
        action_types=["off_platform_payment"], payment_context="off_platform",
    )
    trust, level, score, *_ = _evaluate(url, snaps, claim, sensitive)
    assert trust.off_platform_payment_detected is True
    assert level == "high"


def test_off_platform_keyword_scan_from_text_only():
    # Even if the model didn't flag it, raw text mentioning Zelle trips the scan.
    snaps = [_snap("https://x.shop", body="please pay with cash app")]
    sensitive = SensitiveActionDetection(payment_context="unknown")
    assert detect_off_platform_payment(sensitive, snaps) is True


# --------------------------------------------------------------------------- #
# Plan scenario 6: captcha / blocked                                          #
# --------------------------------------------------------------------------- #

def test_case6_captcha_is_not_safe():
    url = "https://some-ticket-site.com/x"
    snaps = [_snap(url, body="Verify you are human")]
    claim = ClaimExtraction(page_state="blocked_or_captcha")
    sensitive = SensitiveActionDetection(page_state="blocked_or_captcha")
    _, level, score, verdict, *_ = _evaluate(url, snaps, claim, sensitive)
    assert level != "low"  # never "safe" when we couldn't inspect
    assert verdict != "likely_safe_browser_context"


# --------------------------------------------------------------------------- #
# Redirect detection + risk banding + JSON parsing                            #
# --------------------------------------------------------------------------- #

def test_suspicious_redirect_from_shortener():
    snaps = [_snap("https://evil-tickets.shop/x")]
    assert detect_suspicious_redirect("https://bit.ly/abc", snaps) is True


def test_suspicious_redirect_on_domain_change():
    snaps = [_snap("https://landing.shop/x")]
    assert detect_suspicious_redirect("https://start.com/x", snaps) is True


def test_classify_risk_bands():
    assert classify_risk(0) == "low"
    assert classify_risk(29) == "low"
    assert classify_risk(30) == "medium"
    assert classify_risk(59) == "medium"
    assert classify_risk(60) == "high"
    assert classify_risk(100) == "high"


def test_extract_json_tolerates_fences_and_prose():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 2}\n```') == {"a": 2}
    assert extract_json('Here you go: {"a": 3} thanks') == {"a": 3}
    assert extract_json("not json at all") == {}


def test_event_mismatch_raises_risk():
    url = "https://some-resale.shop/x"
    snaps = [_snap(url, body="Taylor Swift at SoFi")]
    claim = ClaimExtraction(
        claimed_platform=None, page_state="login_required",
        claimed_event="Taylor Swift", claimed_venue="SoFi Stadium",
    )
    sensitive = SensitiveActionDetection(
        is_sensitive_action_page=True, page_state="login_required",
        action_types=["login"],
    )
    trust, level, score, *_ = _evaluate(
        url, snaps, claim, sensitive,
        expected_event="Coldplay", expected_venue="MetLife Stadium",
    )
    assert trust.event_reference_mismatch is True
    assert level == "high"


# --- off-platform keyword scan: false-positive guard --------------------------

def test_offplatform_ignores_giftcards_nav_link():
    """A benign 'Gift Cards' footer link must NOT trigger off-platform."""
    snaps = [_snap("https://vividseats.com", body=(
        "Buy tickets. Checkout. Buy Now Pay Later. SHOP Gift Cards Rewards "
        "Vivid Seats App. Contact Us About Us"
    ))]
    assert detect_off_platform_payment(SensitiveActionDetection(), snaps) is False


def test_offplatform_flags_giftcard_with_payment_intent():
    snaps = [_snap("https://x", body="To confirm your seats, pay with a gift card and send the code")]
    assert detect_off_platform_payment(SensitiveActionDetection(), snaps) is True


def test_offplatform_flags_payment_app_name_alone():
    snaps = [_snap("https://x", body="We accept Zelle for all orders")]
    assert detect_off_platform_payment(SensitiveActionDetection(), snaps) is True


def test_offplatform_ignores_crypto_ad_without_payment():
    snaps = [_snap("https://x", body="Trade crypto and bitcoin on our partner exchange banner")]
    assert detect_off_platform_payment(SensitiveActionDetection(), snaps) is False


# --- captcha / blocked handling: trusted vs untrusted -------------------------

def test_trusted_domain_blocked_stays_benign():
    """A whitelisted domain hitting a bot wall is benign, not 'needs review'."""
    snaps = [_snap("https://www.ticketmaster.com/event/x",
                   title="Access Denied", body="Pardon the interruption captcha")]
    claim = ClaimExtraction(claimed_platform="Ticketmaster",
                            claimed_domain="ticketmaster.com",
                            page_state="blocked_or_captcha")
    sensitive = SensitiveActionDetection(page_state="blocked_or_captcha")
    trust, level, score, verdict, summary, rec, ev = evaluate_trust_and_score(
        "https://www.ticketmaster.com/event/x", snaps, claim, sensitive)
    assert level == "low"
    assert verdict == "likely_safe_browser_context"
    assert any("bot-check" in c for c in trust.benign_context)


def test_untrusted_domain_blocked_needs_review():
    """An untrusted blocked site must not be called safe — bump to manual review."""
    snaps = [_snap("https://weirdtix.xyz/e", body="captcha bot check")]
    claim = ClaimExtraction(claimed_platform="WeirdTix",
                            claimed_domain="weirdtix.xyz",
                            page_state="blocked_or_captcha")
    sensitive = SensitiveActionDetection(page_state="blocked_or_captcha")
    _, level, *_ = evaluate_trust_and_score(
        "https://weirdtix.xyz/e", snaps, claim, sensitive)
    assert level == "medium"

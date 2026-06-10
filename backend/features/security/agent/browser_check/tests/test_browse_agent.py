"""Tests for the agent-driven browse loop's deterministic helpers.

These cover the safety gate, the sensitive-surface recorder, and the
worst-surface selection that feeds the scorer — all without a browser or LLM.
"""

from backend.features.security.agent.browser_check.browser_runner import BrowserCheckRunner
from backend.features.security.agent.browser_check.schemas import (
    BrowseDecision,
    BrowserSnapshot,
    ClaimExtraction,
    ClickableElement,
    SensitiveActionDetection,
    SensitiveSurface,
)


def _snap(step=0, url="http://x", *clickables) -> BrowserSnapshot:
    return BrowserSnapshot(step=step, url=url, clickable_elements=list(clickables))


def _el(index, text) -> ClickableElement:
    return ClickableElement(index=index, text=text)


# --------------------------------------------------------------------------- #
# _safe_browse_click — the observe-only safety gate                           #
# --------------------------------------------------------------------------- #

def test_safe_click_returns_element_when_safe():
    runner = BrowserCheckRunner()
    snap = _snap(0, "http://x", _el(3, "Get Tickets"))
    dec = BrowseDecision(action="click", target_index=3, action_label="Get Tickets", safety="safe")
    assert runner._safe_browse_click(snap, dec).index == 3


def test_safe_click_blocks_irreversible_label():
    runner = BrowserCheckRunner()
    snap = _snap(0, "http://x", _el(3, "Pay now"))
    dec = BrowseDecision(action="click", target_index=3, action_label="Pay now", safety="safe")
    assert runner._safe_browse_click(snap, dec) is None


def test_safe_click_blocks_when_element_text_is_unsafe():
    runner = BrowserCheckRunner()
    # Label looks benign but the actual element text is irreversible.
    snap = _snap(0, "http://x", _el(3, "Confirm purchase"))
    dec = BrowseDecision(action="click", target_index=3, action_label="Continue", safety="safe")
    assert runner._safe_browse_click(snap, dec) is None


def test_safe_click_blocks_unsafe_or_uncertain_safety():
    runner = BrowserCheckRunner()
    snap = _snap(0, "http://x", _el(3, "Get Tickets"))
    for s in ("unsafe", "uncertain"):
        dec = BrowseDecision(action="click", target_index=3, action_label="Get Tickets", safety=s)
        assert runner._safe_browse_click(snap, dec) is None


def test_safe_click_none_for_non_click_action():
    runner = BrowserCheckRunner()
    snap = _snap(0, "http://x", _el(3, "Get Tickets"))
    assert runner._safe_browse_click(snap, BrowseDecision(action="finish")) is None


# --------------------------------------------------------------------------- #
# _record_surface — de-duplicated sensitive-page log                          #
# --------------------------------------------------------------------------- #

def test_record_surface_dedupes_same_url_state():
    surfaces: list[SensitiveSurface] = []
    snap = _snap(1, "http://x/login")
    claim = ClaimExtraction(page_state="login_required")
    sens = SensitiveActionDetection(is_sensitive_action_page=True, action_types=["login"])
    BrowserCheckRunner._record_surface(surfaces, snap, claim, sens)
    BrowserCheckRunner._record_surface(surfaces, snap, claim, sens)
    assert len(surfaces) == 1
    assert surfaces[0].page_state == "login_required"


# --------------------------------------------------------------------------- #
# _select_for_verdict — worst-surface selection                              #
# --------------------------------------------------------------------------- #

def _obs(step, page_state, sensitive=False):
    return (
        _snap(step),
        ClaimExtraction(page_state=page_state),
        SensitiveActionDetection(is_sensitive_action_page=sensitive, page_state=page_state),
    )


def test_select_picks_worst_sensitive_surface():
    observations = [
        _obs(0, "event_listing"),
        _obs(1, "off_platform_payment", sensitive=True),  # worst
        _obs(2, "event_listing"),                          # ended back on benign page
    ]
    claim, sens = BrowserCheckRunner._select_for_verdict(observations)
    assert claim.page_state == "off_platform_payment"


def test_select_falls_back_to_last_when_nothing_sensitive():
    observations = [_obs(0, "event_listing"), _obs(1, "quantity_modal"), _obs(2, "ticket_detail")]
    claim, sens = BrowserCheckRunner._select_for_verdict(observations)
    assert claim.page_state == "ticket_detail"  # last/deepest


def test_select_empty_observations_safe_default():
    claim, sens = BrowserCheckRunner._select_for_verdict([])
    assert claim.page_state == "unknown"


# --- early gate: not a ticket site -------------------------------------------

def _gsnap(domain="smalltix.xyz"):
    return BrowserSnapshot(step=0, url=f"http://{domain}/x", registered_domain=domain)


def test_short_circuit_on_non_ticket_site():
    claim = ClaimExtraction(is_ticket_site=False, page_state="unknown")
    assert BrowserCheckRunner._short_circuit_non_ticket(claim, _gsnap("casino.xyz")) is True


def test_no_short_circuit_on_ticket_site():
    claim = ClaimExtraction(is_ticket_site=True, page_state="event_listing")
    assert BrowserCheckRunner._short_circuit_non_ticket(claim, _gsnap()) is False


def test_no_short_circuit_on_trusted_domain():
    # Whitelisted domain is a ticket marketplace even if the model says otherwise.
    claim = ClaimExtraction(is_ticket_site=False)
    assert BrowserCheckRunner._short_circuit_non_ticket(claim, _gsnap("stubhub.com")) is False


def test_no_short_circuit_when_blocked():
    claim = ClaimExtraction(is_ticket_site=False, page_state="blocked_or_captcha")
    assert BrowserCheckRunner._short_circuit_non_ticket(claim, _gsnap("bet365.com")) is False


def test_not_a_ticket_site_result_shape():
    r = BrowserCheckRunner()._not_a_ticket_site_result(
        "http://casino.xyz/x", [_gsnap("casino.xyz")], ClaimExtraction(is_ticket_site=False)
    )
    assert r.verdict == "not_a_ticket_site"
    assert r.is_ticket_site is False
    assert r.risk_score == 0

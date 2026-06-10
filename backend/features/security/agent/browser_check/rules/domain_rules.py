"""Deterministic trust evaluation and risk scoring.

The LLM prompts only *describe* the page (claim / sensitive action). The final
``scam`` decision is made here, by hard-coded rules, so the verdict is auditable
and not at the mercy of a model hallucination.

Core principle: a login / payment page is not a scam by itself. Risk rises when a
sensitive action co-occurs with an *unverified or inconsistent* context — a
suspicious domain, a claimed-brand/domain mismatch, off-platform payment, an
OTP / transfer-code request, a suspicious redirect, or an event mismatch.

Everything here is pure functions over the schema objects — no I/O, no browser,
no LLM — so it is fully unit-testable on its own.
"""

from __future__ import annotations

from typing import Optional

import tldextract

from ..schemas import (
    BrowserSnapshot,
    ClaimExtraction,
    RiskLevel,
    SensitiveActionDetection,
    TrustCheck,
    Verdict,
)

# --------------------------------------------------------------------------- #
# Trusted marketplace config (small + editable on purpose)                    #
# --------------------------------------------------------------------------- #

TRUSTED_TICKET_DOMAINS: dict[str, dict] = {
    "ticketmaster.com": {"platform": "Ticketmaster", "type": "primary"},
    "livenation.com": {"platform": "Live Nation", "type": "primary"},
    "axs.com": {"platform": "AXS", "type": "primary"},
    "seatgeek.com": {"platform": "SeatGeek", "type": "resale"},
    "stubhub.com": {"platform": "StubHub", "type": "resale"},
    "tickpick.com": {"platform": "TickPick", "type": "resale"},
    "vividseats.com": {"platform": "Vivid Seats", "type": "resale"},
    "gametime.co": {"platform": "GameTime", "type": "resale"},
    "eventbrite.com": {"platform": "Eventbrite", "type": "primary"},
    "fifa.com": {"platform": "FIFA", "type": "primary"},
}

# Map a claimed platform name (lowercased) to the domains that legitimately back
# it. Multiple entries allowed (Live Nation tickets sell through Ticketmaster).
PLATFORM_DOMAIN_ALIASES: dict[str, list[str]] = {
    "ticketmaster": ["ticketmaster.com"],
    "live nation": ["livenation.com", "ticketmaster.com"],
    "axs": ["axs.com"],
    "seatgeek": ["seatgeek.com"],
    "stubhub": ["stubhub.com"],
    "tickpick": ["tickpick.com"],
    "vivid seats": ["vividseats.com"],
    "gametime": ["gametime.co"],
    "eventbrite": ["eventbrite.com"],
    "fifa": ["fifa.com"],
}

# Payment-app / off-platform method names whose mere presence on a ticket page is
# itself a strong off-platform-payment signal.
OFF_PLATFORM_STRONG_KEYWORDS: list[str] = [
    "zelle", "venmo", "cash app", "cashapp", "western union",
    "paypal friends and family", "paypal f&f", "friends and family",
]

# Ambiguous terms that ALSO appear in benign navigation / footers / ads (a
# "Gift Cards" shop link, a crypto banner, a "WhatsApp us" support link). These
# count as off-platform ONLY when a payment-intent phrase sits right next to them.
OFF_PLATFORM_CONTEXTUAL_KEYWORDS: list[str] = [
    "gift card", "crypto", "bitcoin", "usdt", "wire transfer",
    "whatsapp", "telegram", "instagram dm", "dm me", "text me",
]

# Phrases that signal an actual request to pay VIA a given method. Deliberately
# specific (not a bare "pay", which is just a checkout button) so they only fire
# in genuine "pay me via X" contexts.
PAYMENT_INTENT_CUES: list[str] = [
    "pay via", "pay with", "pay using", "pay by", "pay me", "payable via",
    "payment via", "payment through", "send payment", "send money", "send $",
    "send funds", "transfer to", "wire to", "e-transfer", "money order",
    "venmo me", "zelle me", "only accept", "accept only",
]

# How close (chars) a payment cue must be to an ambiguous keyword to count.
_OFF_PLATFORM_CONTEXT_WINDOW = 80

URL_SHORTENER_DOMAINS: frozenset[str] = frozenset(
    {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly",
     "rebrand.ly", "cutt.ly", "shorturl.at"}
)

# Page states that constitute an in-flow sensitive decision point.
SENSITIVE_PAGE_STATES = frozenset(
    {"login_required", "payment_required", "ticket_transfer_claim",
     "off_platform_payment"}
)

# --------------------------------------------------------------------------- #
# Scoring weights                                                             #
# --------------------------------------------------------------------------- #

# Strong risk flags (additive).
W_OFF_PLATFORM_PAYMENT = 45
W_BRAND_DOMAIN_MISMATCH = 35
W_SENSITIVE_ON_UNTRUSTED = 30
W_OTP_OR_TRANSFER_CODE = 25
W_PRIVATE_SELLER_PAYMENT = 25
W_SUSPICIOUS_REDIRECT = 20
W_EVENT_MISMATCH = 20
W_LOGIN_ON_UNTRUSTED = 15

# Weak risk flags.
W_URGENCY_WITH_OTHER = 10
W_NO_CLEAR_IDENTITY = 10

# Benign deductions (subtracted).
D_TRUSTED_PLATFORM_MATCH = 25
D_INSIDE_PLATFORM_PAYMENT = 15
D_EVENT_MATCH = 10
D_LISTING_ONLY = 10

# Risk-band edges.
RISK_MEDIUM_MIN = 30
RISK_HIGH_MIN = 60

# Default score when the browser check could not collect reliable evidence.
UNKNOWN_SCORE = 50


# --------------------------------------------------------------------------- #
# Domain helpers                                                              #
# --------------------------------------------------------------------------- #

def registered_domain(url_or_domain: Optional[str]) -> Optional[str]:
    """Return the lowercased registrable domain (eTLD+1), or None.

    Args:
        url_or_domain: A full URL or a bare hostname.

    Returns:
        ``"ticketmaster.com"`` style domain, or None if unparseable.
    """
    if not url_or_domain:
        return None
    ext = tldextract.extract(url_or_domain)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}".lower()
    return None


def is_trusted_domain(domain: Optional[str]) -> bool:
    """Whether ``domain`` is a known, trusted ticket marketplace."""
    return bool(domain) and domain in TRUSTED_TICKET_DOMAINS


def platform_matches_domain(
    claimed_platform: Optional[str],
    current_domain: Optional[str],
    claimed_domain: Optional[str] = None,
) -> Optional[bool]:
    """Whether the claimed platform/brand is consistent with the live domain.

    Args:
        claimed_platform: Brand the page presents itself as (e.g. "Ticketmaster").
        current_domain: The live registrable domain the browser is actually on.
        claimed_domain: A domain the page explicitly claims, if any.

    Returns:
        True if consistent, False if a known brand is on the wrong domain, or
        None if there is no brand claim to check against.
    """
    if not current_domain:
        return None

    # An explicit claimed domain that matches the live domain is consistent.
    if claimed_domain and registered_domain(claimed_domain) == current_domain:
        return True

    if not claimed_platform:
        return None

    aliases = PLATFORM_DOMAIN_ALIASES.get(claimed_platform.lower().strip())
    if not aliases:
        # We don't recognize the claimed brand — can't assert a mismatch.
        return None
    return current_domain in aliases


# --------------------------------------------------------------------------- #
# Signal detectors                                                            #
# --------------------------------------------------------------------------- #

def _contextual_keyword_with_payment(text: str, keyword: str) -> bool:
    """True if ``keyword`` appears within a payment-intent window in ``text``.

    Avoids flagging a benign "Gift Cards" footer link by requiring a "pay via /
    send money / ..." cue near the keyword, not merely anywhere on the page.
    """
    idx = text.find(keyword)
    while idx != -1:
        lo = max(0, idx - _OFF_PLATFORM_CONTEXT_WINDOW)
        hi = idx + len(keyword) + _OFF_PLATFORM_CONTEXT_WINDOW
        window = text[lo:hi]
        if any(cue in window for cue in PAYMENT_INTENT_CUES):
            return True
        idx = text.find(keyword, idx + 1)
    return False


def detect_off_platform_payment(
    sensitive: SensitiveActionDetection, snapshots: list[BrowserSnapshot]
) -> bool:
    """True if off-platform payment was requested (model verdict or text scan)."""
    if sensitive.payment_context == "off_platform":
        return True
    if "off_platform_payment" in sensitive.action_types:
        return True
    if "private_message_seller" in sensitive.action_types:
        return True
    # Belt-and-braces text scan: strong payment-app names trigger on their own;
    # ambiguous terms only when a payment-intent phrase sits next to them.
    for snap in snapshots:
        haystack = f"{snap.body_text} {snap.title or ''}".lower()
        if any(kw in haystack for kw in OFF_PLATFORM_STRONG_KEYWORDS):
            return True
        if any(
            _contextual_keyword_with_payment(haystack, kw)
            for kw in OFF_PLATFORM_CONTEXTUAL_KEYWORDS
        ):
            return True
    return False


def detect_suspicious_redirect(
    input_url: str, snapshots: list[BrowserSnapshot]
) -> bool:
    """True if the page left a URL-shortener or changed registrable domain.

    A simple, conservative heuristic: if the entry URL was a known shortener, or
    the first observed domain differs from the final observed domain, treat it as
    a redirect worth flagging.
    """
    start_domain = registered_domain(input_url)
    observed = [s.registered_domain for s in snapshots if s.registered_domain]

    if start_domain in URL_SHORTENER_DOMAINS:
        return True

    if observed:
        if start_domain and start_domain != observed[0]:
            return True
        if len(set(observed)) > 1:
            return True
    return False


def _event_reference_mismatch(
    claim: ClaimExtraction,
    expected_event: Optional[str],
    expected_venue: Optional[str],
    expected_date: Optional[str],
) -> Optional[bool]:
    """Compare the page's claimed event reference to caller expectations.

    Returns True on a clear conflict, False on a clear match, None if there is
    nothing to compare (no expectations supplied or page revealed nothing).
    """
    expectations = [
        (expected_event, claim.claimed_event),
        (expected_venue, claim.claimed_venue),
        (expected_date, claim.claimed_date_time),
    ]
    checked = [(exp, got) for exp, got in expectations if exp]
    if not checked:
        return None

    any_compared = False
    for exp, got in checked:
        if not got:
            continue
        any_compared = True
        if _loose_contains(exp, got):
            return False  # at least one concrete field matches → trust it
    # We had expectations and the page named the field(s), but none matched.
    return True if any_compared else None


# Generic words that two unrelated events/venues commonly share — excluded from
# the token-overlap check so "MetLife Stadium" != "SoFi Stadium".
_GENERIC_TOKENS = frozenset(
    {"stadium", "arena", "center", "centre", "theatre", "theater", "hall",
     "park", "field", "dome", "the", "and", "vs", "at", "concert", "tour",
     "live", "show", "tickets", "ticket", "event"}
)


def _loose_contains(expected: str, got: str) -> bool:
    """Case-insensitive, whitespace-tolerant overlap check between two strings.

    Generic venue/event filler words are ignored so two different venues that
    merely share "Stadium" are not treated as a match.
    """
    e = " ".join(expected.lower().split())
    g = " ".join(got.lower().split())
    if not e or not g:
        return False
    if e in g or g in e:
        return True
    # Token overlap on *distinctive* tokens only.
    e_tokens = {t for t in e.split() if len(t) > 2 and t not in _GENERIC_TOKENS}
    if not e_tokens:
        return False
    hits = sum(1 for t in e_tokens if t in g)
    return hits >= max(1, len(e_tokens) // 2)


def _has_urgency_language(snapshots: list[BrowserSnapshot]) -> bool:
    """Detect heavy scarcity/urgency marketing language across snapshots."""
    cues = ["only", "last ticket", "selling fast", "hurry", "act now",
            "limited time", "almost gone", "few left", "don't miss"]
    for snap in snapshots:
        text = snap.body_text.lower()
        if sum(1 for c in cues if c in text) >= 2:
            return True
    return False


# --------------------------------------------------------------------------- #
# Trust check + scoring                                                       #
# --------------------------------------------------------------------------- #

def build_trust_check(
    input_url: str,
    snapshots: list[BrowserSnapshot],
    claim: ClaimExtraction,
    sensitive: SensitiveActionDetection,
    expected_event: Optional[str] = None,
    expected_venue: Optional[str] = None,
    expected_date: Optional[str] = None,
) -> TrustCheck:
    """Assemble the deterministic ``TrustCheck`` from the collected evidence."""
    final_domain = (
        snapshots[-1].registered_domain if snapshots else registered_domain(input_url)
    )
    trusted = is_trusted_domain(final_domain)
    matches = platform_matches_domain(
        claim.claimed_platform, final_domain, claim.claimed_domain
    )
    off_platform = detect_off_platform_payment(sensitive, snapshots)
    suspicious_redirect = detect_suspicious_redirect(input_url, snapshots)
    event_mismatch = _event_reference_mismatch(
        claim, expected_event, expected_venue, expected_date
    )

    strong: list[str] = []
    weak: list[str] = []
    benign: list[str] = []

    sensitive_page = (
        sensitive.is_sensitive_action_page
        or claim.page_state in SENSITIVE_PAGE_STATES
    )
    asks_login = (
        "login" in sensitive.action_types
        or "password" in sensitive.action_types
        or claim.page_state == "login_required"
    )
    asks_code = (
        "otp_or_verification_code" in sensitive.action_types
        or "ticket_transfer_code" in sensitive.action_types
    )
    asks_private = "private_message_seller" in sensitive.action_types

    # --- strong flags ---
    if off_platform:
        strong.append("Off-platform payment requested (Zelle/Venmo/crypto/etc.)")
    if matches is False:
        strong.append(
            f"Page claims {claim.claimed_platform} but runs on {final_domain}"
        )
    if sensitive_page and not trusted:
        strong.append("Sensitive action requested on an untrusted domain")
    if asks_code:
        strong.append("Page requests an OTP / verification / transfer code")
    if asks_private:
        strong.append("Page pushes private off-platform contact with the seller")
    if suspicious_redirect:
        strong.append("Suspicious redirect / domain change before landing")
    if event_mismatch:
        strong.append("Event / venue / date conflicts with the expected listing")
    elif asks_login and not trusted and matches is not True:
        strong.append("Login requested on an untrusted / brand-mismatched domain")

    # --- weak flags ---
    if _has_urgency_language(snapshots) and (strong or weak):
        weak.append("Heavy urgency / scarcity language alongside other signals")
    if not claim.claimed_platform and not trusted:
        weak.append("No clear platform identity on an unrecognized domain")

    # --- benign context ---
    if trusted and matches is True:
        benign.append("Trusted marketplace domain with matching brand")
    elif trusted:
        benign.append("Trusted marketplace domain")
    if sensitive.payment_context == "inside_platform" and trusted:
        benign.append("Payment occurs inside the trusted platform checkout")
    if event_mismatch is False:
        benign.append("Event / venue / date matches the expected listing")
    if (
        not sensitive_page
        and claim.page_state in ("event_listing", "quantity_modal")
    ):
        benign.append("Only listing / quantity pages observed; no sensitive action")

    return TrustCheck(
        current_registered_domain=final_domain,
        claimed_domain=claim.claimed_domain,
        is_trusted_marketplace_domain=trusted,
        domain_matches_claimed_platform=matches,
        domain_mismatch_reason=(
            f"Claimed {claim.claimed_platform}, live domain {final_domain}"
            if matches is False else None
        ),
        suspicious_redirect=suspicious_redirect,
        event_reference_mismatch=event_mismatch,
        off_platform_payment_detected=off_platform,
        strong_flags=strong,
        weak_flags=weak,
        benign_context=benign,
    )


def score_from_trust(
    trust: TrustCheck,
    claim: ClaimExtraction,
    sensitive: SensitiveActionDetection,
    snapshots: list[BrowserSnapshot],
) -> int:
    """Map the trust check to a 0-100 risk score (higher = riskier)."""
    score = 0

    sensitive_page = (
        sensitive.is_sensitive_action_page
        or claim.page_state in SENSITIVE_PAGE_STATES
    )
    asks_login = (
        "login" in sensitive.action_types
        or "password" in sensitive.action_types
        or claim.page_state == "login_required"
    )
    asks_code = (
        "otp_or_verification_code" in sensitive.action_types
        or "ticket_transfer_code" in sensitive.action_types
    )
    asks_private = "private_message_seller" in sensitive.action_types

    # strong
    if trust.off_platform_payment_detected:
        score += W_OFF_PLATFORM_PAYMENT
    if trust.domain_matches_claimed_platform is False:
        score += W_BRAND_DOMAIN_MISMATCH
    if sensitive_page and not trust.is_trusted_marketplace_domain:
        score += W_SENSITIVE_ON_UNTRUSTED
    if asks_code:
        score += W_OTP_OR_TRANSFER_CODE
    if asks_private:
        score += W_PRIVATE_SELLER_PAYMENT
    if trust.suspicious_redirect:
        score += W_SUSPICIOUS_REDIRECT
    if trust.event_reference_mismatch:
        score += W_EVENT_MISMATCH
    if (
        asks_login
        and not trust.is_trusted_marketplace_domain
        and trust.domain_matches_claimed_platform is not True
    ):
        score += W_LOGIN_ON_UNTRUSTED

    # weak
    if _has_urgency_language(snapshots) and score > 0:
        score += W_URGENCY_WITH_OTHER
    if not claim.claimed_platform and not trust.is_trusted_marketplace_domain:
        score += W_NO_CLEAR_IDENTITY

    # benign deductions
    if trust.is_trusted_marketplace_domain and trust.domain_matches_claimed_platform is True:
        score -= D_TRUSTED_PLATFORM_MATCH
    if sensitive.payment_context == "inside_platform" and trust.is_trusted_marketplace_domain:
        score -= D_INSIDE_PLATFORM_PAYMENT
    if trust.event_reference_mismatch is False:
        score -= D_EVENT_MATCH
    if (
        not sensitive_page
        and claim.page_state in ("event_listing", "quantity_modal")
    ):
        score -= D_LISTING_ONLY

    return max(0, min(100, score))


def classify_risk(score: int) -> RiskLevel:
    """Map a 0-100 risk score to a coarse band."""
    if score >= RISK_HIGH_MIN:
        return "high"
    if score >= RISK_MEDIUM_MIN:
        return "medium"
    return "low"


def verdict_for(risk_level: RiskLevel, browser_failed: bool = False) -> Verdict:
    """Map a risk band (or failure) to the public verdict enum."""
    if browser_failed or risk_level == "unknown":
        return "unknown_browser_check_failed"
    if risk_level == "high":
        return "high_risk_likely_ticket_scam"
    if risk_level == "medium":
        return "suspicious_needs_manual_review"
    return "likely_safe_browser_context"


def _recommended_action(risk_level: RiskLevel, trust: TrustCheck) -> str:
    """A short, user-facing next step matched to the verdict."""
    if risk_level == "high":
        return (
            "Do not enter credentials, payment details, OTP, or transfer codes. "
            "Verify the event directly on the official ticket platform or venue "
            "website before paying anyone."
        )
    if risk_level == "medium":
        return (
            "Proceed with caution and verify the seller/event through the "
            "official platform. Never pay via Zelle/Venmo/Cash App/crypto/gift "
            "card or accept a private off-platform transfer."
        )
    if risk_level == "unknown":
        return (
            "Browser inspection was inconclusive. Do not rely on this result; "
            "verify manually or use the other security modules."
        )
    return (
        "Continue only through the official platform checkout. Do not leave the "
        "platform for private payment."
    )


def _summary(risk_level: RiskLevel, claim: ClaimExtraction, trust: TrustCheck) -> str:
    """A one-line human summary of the verdict."""
    domain = trust.current_registered_domain or "the page"
    platform = claim.claimed_platform or "an unidentified platform"
    if risk_level == "high":
        return (
            f"The page presents as {platform} but shows strong scam signals on "
            f"{domain} ({'; '.join(trust.strong_flags[:2]) or 'inconsistent context'})."
        )
    if risk_level == "medium":
        return (
            f"The page on {domain} has uncertain signals and warrants manual "
            f"review before any purchase."
        )
    if risk_level == "unknown":
        return "Browser check could not collect reliable evidence."
    return (
        f"The page appears to be a legitimate {platform} flow on {domain} with no "
        f"strong scam signals in the browser context."
    )


def evaluate_trust_and_score(
    input_url: str,
    snapshots: list[BrowserSnapshot],
    claim: ClaimExtraction,
    sensitive: SensitiveActionDetection,
    expected_event: Optional[str] = None,
    expected_venue: Optional[str] = None,
    expected_date: Optional[str] = None,
) -> tuple[TrustCheck, RiskLevel, int, Verdict, str, str, list[str]]:
    """Full deterministic verdict: trust check → score → level → verdict → text.

    Returns:
        ``(trust, risk_level, risk_score, verdict, summary, recommended_action,
        evidence)``.
    """
    trust = build_trust_check(
        input_url, snapshots, claim, sensitive,
        expected_event, expected_venue, expected_date,
    )
    score = score_from_trust(trust, claim, sensitive, snapshots)
    risk_level = classify_risk(score)

    # A captcha / bot-check / error page means we could NOT inspect the purchase
    # flow. For a TRUSTED whitelisted domain this is expected anti-bot behaviour,
    # not a scam signal — report it as blocked-but-benign. For any other domain we
    # must not call it safe; bump to manual review (an untrusted blocked site is
    # then typically driven by the OSINT reputation folded in afterwards).
    blocked = claim.page_state in ("blocked_or_captcha", "error_page")
    if blocked and trust.is_trusted_marketplace_domain:
        trust.benign_context.append(
            f"Trusted domain returned a bot-check ({claim.page_state}); not inspected."
        )
    elif blocked and risk_level == "low":
        risk_level = "medium"
        score = max(score, RISK_MEDIUM_MIN)
        trust.weak_flags.append(
            f"Could not inspect the purchase flow ({claim.page_state})"
        )

    verdict = verdict_for(risk_level)
    summary = _summary(risk_level, claim, trust)
    if blocked and trust.is_trusted_marketplace_domain:
        summary = (
            f"{trust.current_registered_domain or 'The trusted domain'} returned a "
            f"bot-check/captcha; the purchase flow could not be inspected, but the "
            f"domain is a trusted marketplace."
        )
    rec = _recommended_action(risk_level, trust)

    evidence: list[str] = []
    if trust.current_registered_domain:
        evidence.append(f"Live registered domain is {trust.current_registered_domain}")
    if claim.claimed_platform:
        evidence.append(f"Page claims platform: {claim.claimed_platform}")
    evidence.extend(trust.strong_flags)
    evidence.extend(trust.weak_flags)
    evidence.extend(trust.benign_context)

    return trust, risk_level, score, verdict, summary, rec, evidence

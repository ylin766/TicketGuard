"""Pydantic schemas for the browser security check.

These are the stable contract the rest of the system consumes. Every model
tolerates missing fields (sane defaults) so a partial / failed browser run still
produces a valid, JSON-serializable ``BrowserSecurityResult``.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high", "unknown"]

PageState = Literal[
    "event_listing",
    "quantity_modal",
    "ticket_detail",
    "login_required",
    "payment_required",
    "ticket_transfer_claim",
    "off_platform_payment",
    "blocked_or_captcha",
    "error_page",
    "unknown",
]

ActionType = Literal[
    "login",
    "password",
    "otp_or_verification_code",
    "payment",
    "billing_info",
    "ticket_transfer",
    "ticket_transfer_code",
    "wallet_connect",
    "off_platform_payment",
    "private_message_seller",
    "download_app",
    "none",
]

MarketplaceType = Literal["primary", "resale", "venue", "social", "unknown"]
PaymentContext = Literal["inside_platform", "off_platform", "unknown", "none"]
Confidence = Literal["high", "medium", "low"]
Verdict = Literal[
    "likely_safe_browser_context",
    "suspicious_needs_manual_review",
    "high_risk_likely_ticket_scam",
    "unknown_browser_check_failed",
]


class ClickableElement(BaseModel):
    """One interactive element offered to the transition-ranking prompt."""

    index: int
    text: str = ""
    tag: Optional[str] = None
    role: Optional[str] = None
    aria_label: Optional[str] = None
    href: Optional[str] = None
    bbox: Optional[dict] = None


class BrowserSnapshot(BaseModel):
    """A single observation of the page at one step."""

    step: int
    url: str = ""
    registered_domain: Optional[str] = None
    title: Optional[str] = None
    screenshot_path: Optional[str] = None
    body_text: str = ""
    html_excerpt: str = ""
    clickable_elements: list[ClickableElement] = Field(default_factory=list)
    error: Optional[str] = None


class ClaimExtraction(BaseModel):
    """What the page *claims* to be — never a scam decision (Prompt 1 output)."""

    claimed_platform: Optional[str] = None
    claimed_domain: Optional[str] = None
    marketplace_type: MarketplaceType = "unknown"
    claimed_event: Optional[str] = None
    claimed_venue: Optional[str] = None
    claimed_city_state: Optional[str] = None
    claimed_date_time: Optional[str] = None
    visible_price_range: Optional[str] = None
    page_state: PageState = "unknown"
    confidence: Confidence = "low"
    evidence: list[str] = Field(default_factory=list)


class SensitiveActionDetection(BaseModel):
    """Whether the page asks for a sensitive action (Prompt 2 output)."""

    is_sensitive_action_page: bool = False
    page_state: PageState = "unknown"
    action_types: list[ActionType] = Field(default_factory=list)
    payment_context: PaymentContext = "none"
    payment_methods: list[str] = Field(default_factory=list)
    requested_inputs: list[str] = Field(default_factory=list)
    irreversible_action_visible: bool = False
    evidence: list[str] = Field(default_factory=list)


class TransitionDecision(BaseModel):
    """The single safe click the ranker chose, if any (Prompt 3 output)."""

    should_click: bool = False
    chosen_index: Optional[int] = None
    action_label: Optional[str] = None
    reason: str = ""
    safety: Literal["safe", "unsafe", "uncertain"] = "uncertain"


class TransitionRecord(BaseModel):
    """An audit record of one probe step (clicked or stopped)."""

    step: int
    before_url: str
    clicked_index: Optional[int] = None
    clicked_text: Optional[str] = None
    after_url: Optional[str] = None
    page_state_before: PageState = "unknown"
    page_state_after: PageState = "unknown"
    stopped_reason: Optional[str] = None


class TrustCheck(BaseModel):
    """Deterministic domain / platform / payment consistency verdict."""

    current_registered_domain: Optional[str] = None
    claimed_domain: Optional[str] = None
    is_trusted_marketplace_domain: bool = False
    domain_matches_claimed_platform: Optional[bool] = None
    domain_mismatch_reason: Optional[str] = None
    suspicious_redirect: bool = False
    event_reference_mismatch: Optional[bool] = None
    off_platform_payment_detected: bool = False
    strong_flags: list[str] = Field(default_factory=list)
    weak_flags: list[str] = Field(default_factory=list)
    benign_context: list[str] = Field(default_factory=list)


class BrowserSecurityResult(BaseModel):
    """The full, stable output returned to the parent ADK agent."""

    module: str = "browser_security_check"
    input_url: str
    final_url: Optional[str] = None
    risk_level: RiskLevel
    risk_score: int = Field(ge=0, le=100)
    verdict: Verdict
    summary: str
    claim: ClaimExtraction = Field(default_factory=ClaimExtraction)
    sensitive_action: SensitiveActionDetection = Field(
        default_factory=SensitiveActionDetection
    )
    trust_check: TrustCheck = Field(default_factory=TrustCheck)
    transitions: list[TransitionRecord] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    recommended_action: str = ""
    snapshots: list[BrowserSnapshot] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

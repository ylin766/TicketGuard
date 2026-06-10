"""Browser-based ticket-scam security check (Layer 2, visual).

Given a ticket-selling URL, open it in a controlled ``browser_use`` session,
observe the real page, safely probe up to ``max_click_depth`` purchase-flow
transitions, detect sensitive ticket actions (login / payment / transfer /
off-platform payment), verify platform/domain consistency, and return a
deterministic, evidence-backed risk signal.

Design principle (PhishVLM-inspired, simplified for ticket scams): a login or
payment page is NOT a scam by itself — it is a sensitive *decision point*. Risk
rises only when a sensitive action co-occurs with an unverified or inconsistent
context (suspicious domain, brand/domain mismatch, off-platform payment, OTP /
transfer-code request, ...).

Public surface:
    browser_security_check(url, ...) -> dict   # the ADK FunctionTool entry point
    BrowserSecurityResult                      # the structured result schema
"""

from .schemas import BrowserSecurityResult

__all__ = ["BrowserSecurityResult", "browser_security_check"]


def browser_security_check(*args, **kwargs):  # pragma: no cover - thin re-export
    """Lazy re-export so importing this package never eagerly pulls in browser_use.

    The heavy ``browser_use`` / ``google.genai`` imports live inside
    ``browser_security_tool`` and ``browser_runner``; importing them only when the
    tool is actually called keeps ``schemas`` / ``domain_rules`` importable (and
    testable) without the runtime browser stack installed.
    """
    from .browser_security_tool import browser_security_check as _impl

    return _impl(*args, **kwargs)

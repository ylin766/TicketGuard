"""ADK FunctionTool entry point for the browser security check.

This is the single function the parent agent (or orchestrator) calls. It opens
the ticket URL in a controlled browser, safely probes up to ``max_click_depth``
purchase-flow transitions, and returns a structured ``BrowserSecurityResult`` as
a plain dict.

Safety contract: this tool NEVER enters personal information, credentials, OTP,
transfer codes, or payment details, and NEVER confirms a purchase or transfer.
"""

from __future__ import annotations

from typing import Any, Optional

from .browser_runner import BrowserCheckRunner


async def browser_security_check(
    url: str,
    expected_event: Optional[str] = None,
    expected_venue: Optional[str] = None,
    expected_date: Optional[str] = None,
    max_click_depth: int = 2,
) -> dict[str, Any]:
    """Browser-based ticket-scam security check.

    Opens the ticket URL in a controlled browser, captures the real page, safely
    probes up to ``max_click_depth`` purchase-flow transitions, detects sensitive
    ticket actions, checks domain/platform/payment consistency, and returns a
    structured browser-risk result.

    Never enters personal information, credentials, OTP, transfer codes, or
    payment details, and never confirms any purchase/transfer.

    Args:
        url: The ticket-selling URL to inspect.
        expected_event: Optional event name the caller expects (cross-check).
        expected_venue: Optional venue the caller expects (cross-check).
        expected_date: Optional date/time the caller expects (cross-check).
        max_click_depth: Max safe purchase-flow clicks (hard-capped at 2).

    Returns:
        A ``BrowserSecurityResult`` as a JSON-serializable dict.
    """
    runner = BrowserCheckRunner(max_click_depth=max_click_depth)
    result = await runner.run(
        url=url,
        expected_event=expected_event,
        expected_venue=expected_venue,
        expected_date=expected_date,
    )
    return result.model_dump()

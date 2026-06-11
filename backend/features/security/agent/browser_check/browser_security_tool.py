"""ADK FunctionTool entry point for the browser security check.

This is the single function the parent agent (or orchestrator) calls. It opens
the ticket URL in a controlled browser and lets a guard-railed agent explore up
to ``max_actions`` steps, returning a structured ``BrowserSecurityResult`` as a
plain dict.

Safety contract: this tool NEVER enters personal information, credentials, OTP,
transfer codes, or payment details, and NEVER confirms a purchase or transfer.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .browser_runner import BrowserCheckRunner
from .osint.osint_escalation import escalate, should_escalate


async def browser_security_check(
    url: str,
    expected_event: Optional[str] = None,
    expected_venue: Optional[str] = None,
    expected_date: Optional[str] = None,
    max_actions: int = 8,
    enable_osint: bool = True,
    headless: bool = True,
    on_frame: Optional[Callable[[int, bytes, str], None]] = None,
    react_instruction: Optional[str] = None,
) -> dict[str, Any]:
    """Browser-based ticket-scam security check.

    Opens the ticket URL in a controlled browser and lets a guard-railed agent
    explore the site (clicking deeper, retreating, finishing on its own) to find
    which sensitive surfaces it leads to, detects sensitive ticket actions, checks
    domain/platform/payment consistency, and returns a structured browser-risk
    result.

    Never enters personal information, credentials, OTP, transfer codes, or
    payment details, and never confirms any purchase/transfer.

    Args:
        url: The ticket-selling URL to inspect.
        expected_event: Optional event name the caller expects (cross-check).
        expected_venue: Optional venue the caller expects (cross-check).
        expected_date: Optional date/time the caller expects (cross-check).
        max_actions: Agent action budget — clicks / go-backs before it must stop
            (hard-capped at 20).
        enable_osint: When True (default), escalate unfamiliar sites with no
            recognizable brand to the OSINT reputation subagent and fold its
            trust rating into the result.
        headless: Run the browser headless (default). Set False to use a headed
            browser, which is far less likely to trip enterprise bot-detection.

    Returns:
        A ``BrowserSecurityResult`` as a JSON-serializable dict.
    """
    runner = BrowserCheckRunner(
        max_actions=max_actions, headless=headless, on_frame=on_frame,
        react_instruction=react_instruction,
    )
    result = await runner.run(
        url=url,
        expected_event=expected_event,
        expected_venue=expected_venue,
        expected_date=expected_date,
    )

    # Unfamiliar domain with no recognizable brand: the deterministic rules are
    # blind here, so consult OSINT reputation before returning.
    if enable_osint and should_escalate(result):
        result = await escalate(result)

    return result.model_dump()

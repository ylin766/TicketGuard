"""Browser-based security agent — the visual (Layer 2) judgement step.

The deterministic pipeline writes its structured evidence to session state under
SECURITY_RESULT. This LLM agent inspects a suspicious ticket URL *in a real
browser* via the ``browser_security_check`` tool, which opens the page, safely
probes up to two purchase-flow transitions, and returns a structured,
evidence-backed browser-risk result.

SECURITY_RESULT (ctx.session.state["security_result"]) is shaped like:
    {
        "status": "ok",                 # "ok" | "unavailable"
        "findings": [...],              # threat verdicts (threat is True/False)
        "context": [...],               # non-threat intelligence (threat is None)
        "flagged": True,                # any finding reported threat is True
        "detail": "...",                # human-readable one-line summary
    }

Design principle: a login or payment page is NOT a scam by itself. Risk rises
only when a sensitive action co-occurs with an unverified or inconsistent
context (brand/domain mismatch, off-platform payment, OTP / transfer-code
request, suspicious redirect, event mismatch). The browser tool encodes that.
"""

from google.adk.agents import LlmAgent

from ....core.config import GEMINI_MODEL
from ....core.state_keys import SECURITY_RESULT  # noqa: F401 - evidence key for the agent
from .browser_check.browser_security_tool import browser_security_check

BROWSER_SECURITY_INSTRUCTION = """\
You are the browser-based security step in a larger ticket-scam detection system.

Use the browser_security_check tool for any ticket URL that needs browser
inspection. Pass the expected event / venue / date when the caller provides them.

Return only the tool result JSON. Do not guess beyond the evidence returned by
the tool. Do not classify a login or payment page as a scam by itself — rely on
the tool's context and evidence (domain match, off-platform payment, transfer-code
requests, redirects). Never instruct the tool to enter credentials, payment
details, OTP, or to confirm a purchase or transfer.
"""

browser_security_agent = LlmAgent(
    name="ticket_browser_security_agent",
    model=GEMINI_MODEL,
    description="Browser-based security checker for ticket-selling links.",
    instruction=BROWSER_SECURITY_INSTRUCTION,
    tools=[browser_security_check],
)

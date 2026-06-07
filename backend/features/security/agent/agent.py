"""Security agent layer — the LLM judgement steps.

This module defines two agents:

* ``browser_security_agent`` — the visual (Layer 2) browser probe. It inspects a
  suspicious ticket URL *in a real browser* via the ``browser_security_check``
  tool, which opens the page, safely probes up to two purchase-flow transitions,
  and returns a structured, evidence-backed browser-risk result.
* ``content_audit_agent`` — the grey-zone LLM orchestrator. It delegates to
  subagents (currently the OSINT subagent) to reach a final grey-zone verdict.

Both read the deterministic pipeline's structured evidence from session state
under SECURITY_RESULT (ctx.session.state["security_result"]), shaped like:
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

from google.adk.agents import LlmAgent, SequentialAgent

from ....core.config import GEMINI_MODEL
from ....core.state_keys import SECURITY_RESULT  # noqa: F401 - evidence key for the agent
from .browser_check.browser_security_tool import browser_security_check
from .osint_subagent import osint_subagent

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

# The content_audit_agent acts as the main grey-zone LLM orchestrator.
# It currently delegates the investigation to the OSINT subagent.
# Future subagents (e.g. screenshot analysis, WHOIS deep-dive) can be added here.
content_audit_agent = SequentialAgent(
    name="content_audit_agent",
    sub_agents=[osint_subagent],
    description="Main security LLM agent that orchestrates subagents like OSINT to make a final grey-zone verdict based on SECURITY_RESULT.",
)

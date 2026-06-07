"""Security agent layer — the LLM part of the workflow.

Exposes:
* ``browser_security_agent``: a Gemini ``LlmAgent`` that inspects a suspicious
  ticket URL in a real browser (via the ``browser_security_check`` tool) and
  returns a structured, evidence-backed risk verdict.
* ``content_audit_agent``: the grey-zone LLM orchestrator that delegates to
  subagents (currently OSINT) for a final grey-zone verdict.
"""

from .agent import browser_security_agent, content_audit_agent

__all__ = ["browser_security_agent", "content_audit_agent"]

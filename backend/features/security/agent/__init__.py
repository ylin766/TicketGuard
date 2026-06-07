"""Security agent layer — the LLM part of the workflow.

Exposes ``browser_security_agent``: a Gemini ``LlmAgent`` that inspects a
suspicious ticket URL in a real browser (via the ``browser_security_check`` tool)
and returns a structured, evidence-backed risk verdict.
"""

from .agent import browser_security_agent

__all__ = ["browser_security_agent"]

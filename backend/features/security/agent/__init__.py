"""Security agent layer — the LLM part of the workflow.

Two components, imported directly by their consumers (this package re-exports
nothing itself):

* ``browser_check/`` — the browser security check: a ReAct browser explorer plus
  OSINT escalation, exposed as the ``browser_security_check`` tool the security
  orchestrator calls in the grey zone.
* ``osint/`` — the OSINT reputation subagent the browser check escalates to for
  unfamiliar (non-whitelisted) sites.
"""

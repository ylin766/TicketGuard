"""ADK entry point.

Re-exports the orchestration ``root_agent`` defined in :mod:`backend.core.agent`
so ADK tooling (``adk run`` / ``adk web``) can discover it here.
"""

from .core.agent import root_agent

__all__ = ["root_agent"]

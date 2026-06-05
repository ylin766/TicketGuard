"""TicketGuard backend package.

Exposes ``root_agent`` so the whole workflow can be launched with::

    adk web        # from this folder's parent
    adk run backend
"""

from .agent import root_agent

__all__ = ["root_agent"]

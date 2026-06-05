"""Core orchestration layer.

Owns the global workflow (preprocess -> parallel features) and the cross-feature
contract (shared state keys). Each feature reads the page from state and writes
its own ``*_result`` back.
"""

from .agent import root_agent

__all__ = ["root_agent"]

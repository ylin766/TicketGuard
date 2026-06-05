"""Security feature — website credibility audit.

Two-part workflow, orchestrated by ``security_orchestrator``:
1. pipeline: deterministic, hard-coded threat-intel detectors + weighted score.
2. agent: an LLM that handles the part the pipeline cannot decide on its own.

Exposes ``security_orchestrator`` for the core orchestration layer.
"""

from .orchestrator import security_orchestrator

__all__ = ["security_orchestrator"]

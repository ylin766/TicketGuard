"""Security pipeline — the deterministic, hard-coded part of the workflow.

``run_pipeline(url)`` queries the threat-intel aggregator and returns each
source's raw risk findings. No LLM, no session state, no synthesized score:
pure input (url) -> output (dict).
"""

from .threatintel import run_threatintel

__all__ = ["run_pipeline"]


def run_pipeline(url: str) -> dict:
    """Evaluate a URL against the threat-intel aggregator.

    Args:
        url: The full ticket-listing URL to evaluate.

    Returns:
        dict with keys: status, findings (each source's native report),
        flagged (any source reported a threat), detail.
    """
    return run_threatintel(url)

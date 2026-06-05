"""Security pipeline — the deterministic, hard-coded part of the workflow.

``run_pipeline(url)`` runs both detectors in parallel and returns the weighted
trust score. No LLM, no session state: pure input (url) -> output (dict).
"""

from concurrent.futures import ThreadPoolExecutor

from .intelowl import run_intelowl
from .scoring import aggregate
from .spiderfoot import run_spiderfoot

__all__ = ["run_pipeline"]


def run_pipeline(url: str) -> dict:
    """Run all detectors on a URL and return the aggregated trust score.

    Args:
        url: The full ticket-listing URL to evaluate.

    Returns:
        dict with keys: score (0-100, higher = safer), flags, detail.
    """
    with ThreadPoolExecutor(max_workers=2) as pool:
        intelowl_future = pool.submit(run_intelowl, url)
        spiderfoot_future = pool.submit(run_spiderfoot, url)
        results = {
            "intelowl": intelowl_future.result(),
            "spiderfoot": spiderfoot_future.result(),
        }
    return aggregate(results)

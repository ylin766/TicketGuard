"""HTTP utilities for the security pipeline with progressive timeout retries."""

import logging
import time

import requests

logger = logging.getLogger(__name__)

# Timeout strategy (seconds) tuned from measured source response times.
# Fast APIs: two short tries.
DEFAULT_TIMEOUT_LEVELS = [4, 6]
# Slow/flaky APIs (e.g., crt.sh, RDAP): longer read budget — these can wait.
SLOW_TIMEOUT_LEVELS = [8, 12]
# CheckPhish never completes inside the pipeline budget; give it a short
# fast-fail timeout so it drops out quickly instead of stalling the scan.
CHECKPHISH_TIMEOUT_LEVELS = [2, 3]


def fetch_with_retry(
    method: str, url: str, timeout_levels: list[int] | None = None, **kwargs
) -> requests.Response:
    """Execute an HTTP request with progressive timeouts and a maximum retry cap.

    If the request fails due to a timeout or connection error, it retries using the next
    timeout value in `timeout_levels`. Once all levels are exhausted, it raises the final
    exception.
    """
    levels = timeout_levels or DEFAULT_TIMEOUT_LEVELS
    last_exception = None

    for i, timeout in enumerate(levels):
        try:
            return requests.request(method, url, timeout=timeout, **kwargs)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exception = e
            if i < len(levels) - 1:
                logger.warning(
                    f"Request to {url} failed (timeout={timeout}s). Retrying... "
                    f"({i + 1}/{len(levels)} attempts used)"
                )
                time.sleep(0.3)  # small backoff before retrying

    if last_exception:
        raise last_exception
    raise RuntimeError("No timeout levels provided to fetch_with_retry.")

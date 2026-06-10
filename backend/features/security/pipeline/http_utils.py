"""HTTP utilities for the security pipeline with progressive timeout retries."""

import logging
import time

import requests

logger = logging.getLogger(__name__)

# TESTING: timeouts lowered for fast iteration (was [3, 5] / [4, 7]).
# Fast APIs: single short try.
DEFAULT_TIMEOUT_LEVELS = [2, 3]
# Slow/flaky APIs (e.g., crt.sh, RDAP): single slightly longer try.
SLOW_TIMEOUT_LEVELS = [3, 4]


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

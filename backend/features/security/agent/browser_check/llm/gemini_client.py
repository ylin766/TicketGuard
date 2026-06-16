"""Gemini JSON helper for the browser security check.

Wraps ``google.genai`` so each of the three prompts returns a validated Pydantic
object. The client is created lazily on first use so importing this module never
requires ``GOOGLE_API_KEY`` (keeps the pure-logic layers testable in isolation).

Screenshots are passed to the model when available — ticket pages lean heavily on
visual seat maps and listing cards, so vision materially improves extraction.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

try:  # Load backend/.env so GOOGLE_API_KEY / GEMINI_MODEL are picked up in any
    from dotenv import load_dotenv  # run mode (ADK already loads it; this covers
                                    # standalone scripts and tests too).
    # backend/ is 5 levels up from this file (browser_check/agent/security/features).
    _BACKEND_ENV = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..", "..", ".env"
    )
    load_dotenv(_BACKEND_ENV)       # explicit path: works regardless of cwd
    load_dotenv()                   # also honor a .env in the current directory
except Exception:  # noqa: BLE001 - python-dotenv optional; env may be set directly
    pass

from .prompts import (
    BROWSE_AGENT_PROMPT,
    CLAIM_EXTRACTION_PROMPT,
    SENSITIVE_ACTION_PROMPT,
    TRANSITION_RANKING_PROMPT,
)
from ..schemas import (
    BrowseDecision,
    BrowserSnapshot,
    ClaimExtraction,
    SensitiveActionDetection,
    TransitionDecision,
)

logger = logging.getLogger("ticketguard.browser_check.gemini")

# Same source/default as backend.core.config, read directly to avoid a fragile
# deep relative import and keep this module standalone-importable for tests.
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

_MAX_TEXT_CHARS = 9000
_MAX_CLICKABLES = 80

_client = None  # lazily initialized google.genai.Client


def _get_client():
    """Return a cached ``google.genai.Client`` (created on first call)."""
    global _client
    if _client is None:
        from backend.core.config import build_genai_client

        _client = build_genai_client()
    return _client


def _format_clickables(snapshot: BrowserSnapshot, max_items: int = _MAX_CLICKABLES) -> str:
    """Render clickable elements as one indexed line each for the prompt."""
    lines = []
    for e in snapshot.clickable_elements[:max_items]:
        parts = [f"Index {e.index}"]
        if e.text:
            parts.append(f"text={e.text!r}")
        if e.tag:
            parts.append(f"tag={e.tag!r}")
        if e.role:
            parts.append(f"role={e.role!r}")
        if e.aria_label:
            parts.append(f"aria_label={e.aria_label!r}")
        if e.href:
            parts.append(f"href={e.href!r}")
        lines.append(" | ".join(parts))
    return "\n".join(lines) if lines else "(none captured)"


def extract_json(text: str) -> dict:
    """Parse a model response into a dict, tolerating markdown fences / prose.

    Args:
        text: The raw model output.

    Returns:
        The parsed dict, or ``{}`` if nothing parseable is found.
    """
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001 - fall through to lenient extraction
        pass

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except Exception:  # noqa: BLE001
        pass

    # Last resort: grab the first balanced-looking {...} block.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except Exception:  # noqa: BLE001
            pass

    logger.warning("could not parse Gemini JSON: %r", text[:200])
    return {}


# Transient Gemini errors worth retrying with backoff (server overload / rate limit).
_RETRYABLE_STATUS = (429, 500, 502, 503, 504)
_MAX_GEMINI_RETRIES = 3
_RETRY_BACKOFF_SECONDS = (2, 5, 10)


def _is_retryable(exc: Exception) -> bool:
    """True if an exception looks like a transient, retry-worthy Gemini error."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in _RETRYABLE_STATUS:
        return True
    name = type(exc).__name__.lower()
    if any(s in name for s in ("remoteprotocol", "connect", "timeout", "readerror")):
        return True
    text = str(exc).lower()
    if any(s in text for s in ("server disconnected", "disconnected", "connection",
                               "timed out", "timeout", "protocol error")):
        return True
    return any(s in text for s in ("503", "unavailable", "high demand",
                                   "overloaded", "429", "rate limit", "try again"))


def _gemini_json(prompt: str, screenshot_path: Optional[str] = None) -> dict:
    """Call Gemini for a JSON object, attaching a screenshot if present.

    Retries transient server errors (503/429/...) with backoff so a momentary
    "model is overloaded" spike doesn't sink the whole browser run.
    """
    import time

    from google.genai import types  # lazy: only needed at call time

    contents: list = [prompt]
    if screenshot_path and os.path.exists(screenshot_path):
        try:
            with open(screenshot_path, "rb") as f:
                image_bytes = f.read()
            contents.append(
                types.Part.from_bytes(data=image_bytes, mime_type="image/png")
            )
        except Exception as exc:  # noqa: BLE001 - vision is best-effort
            logger.debug("could not attach screenshot %s: %s", screenshot_path, exc)

    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_GEMINI_RETRIES + 1):
        try:
            resp = _get_client().models.generate_content(
                model=MODEL_NAME,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                ),
            )
            return extract_json(resp.text or "{}")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < _MAX_GEMINI_RETRIES and _is_retryable(exc):
                delay = _RETRY_BACKOFF_SECONDS[min(attempt, len(_RETRY_BACKOFF_SECONDS) - 1)]
                logger.warning(
                    "Gemini transient error (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1, _MAX_GEMINI_RETRIES, delay, str(exc)[:120],
                )
                time.sleep(delay)
                continue
            raise
    raise last_exc  # pragma: no cover - loop always returns or raises above


def classify_claim(
    snapshot: BrowserSnapshot,
    expected_event: Optional[str] = None,
    expected_venue: Optional[str] = None,
    expected_date: Optional[str] = None,
) -> ClaimExtraction:
    """Prompt 1: extract what the page claims to be (never a scam decision)."""
    prompt = CLAIM_EXTRACTION_PROMPT.format(
        url=snapshot.url,
        registered_domain=snapshot.registered_domain,
        title=snapshot.title or "",
        text=snapshot.body_text[:_MAX_TEXT_CHARS],
        clickables=_format_clickables(snapshot),
        expected_event=expected_event,
        expected_venue=expected_venue,
        expected_date=expected_date,
    )
    data = _gemini_json(prompt, snapshot.screenshot_path)
    try:
        return ClaimExtraction.model_validate(data)
    except Exception as exc:  # noqa: BLE001 - never let a bad shape crash the run
        logger.warning("claim validation failed: %s", exc)
        return ClaimExtraction()


def classify_sensitive_action(
    snapshot: BrowserSnapshot, claim: ClaimExtraction
) -> SensitiveActionDetection:
    """Prompt 2: detect whether the page asks for a sensitive action."""
    prompt = SENSITIVE_ACTION_PROMPT.format(
        url=snapshot.url,
        registered_domain=snapshot.registered_domain,
        title=snapshot.title or "",
        claim_json=claim.model_dump_json(indent=2),
        text=snapshot.body_text[:_MAX_TEXT_CHARS],
        clickables=_format_clickables(snapshot),
    )
    data = _gemini_json(prompt, snapshot.screenshot_path)
    try:
        return SensitiveActionDetection.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("sensitive-action validation failed: %s", exc)
        return SensitiveActionDetection()


def rank_transition(
    snapshot: BrowserSnapshot,
    claim: ClaimExtraction,
    sensitive: SensitiveActionDetection,
) -> TransitionDecision:
    """Prompt 3 (legacy): pick at most one safe click to advance the flow.

    Superseded by :func:`decide_browse_action`; kept for reference / reuse.
    """
    prompt = TRANSITION_RANKING_PROMPT.format(
        url=snapshot.url,
        page_state=claim.page_state,
        claim_json=claim.model_dump_json(indent=2),
        sensitive_json=sensitive.model_dump_json(indent=2),
        clickables=_format_clickables(snapshot),
    )
    data = _gemini_json(prompt, snapshot.screenshot_path)
    try:
        return TransitionDecision.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("transition validation failed: %s", exc)
        return TransitionDecision(should_click=False, reason="parse_error")


def decide_browse_action(
    snapshot: BrowserSnapshot,
    claim: ClaimExtraction,
    sensitive: SensitiveActionDetection,
    *,
    history: list[str],
    surfaces: list[str],
    visited: list[str],
    budget_left: int,
    restricted: bool,
) -> BrowseDecision:
    """Prompt 3b: the agent picks one action (click / go_back / finish).

    Args:
        snapshot: The current page observation.
        claim / sensitive: This page's extracted claim and sensitive-action read.
        history: One line per prior action, most recent last.
        surfaces: One line per sensitive surface already discovered.
        visited: URLs already seen, so the agent doesn't re-tread them.
        budget_left: Remaining actions before the hard cap stops exploration.
        restricted: True if the current page is sensitive or un-inspectable, so
            only ``go_back`` / ``finish`` are valid.
    """
    prompt = BROWSE_AGENT_PROMPT.format(
        url=snapshot.url,
        page_state=claim.page_state,
        restricted=restricted,
        budget_left=budget_left,
        claim_json=claim.model_dump_json(indent=2),
        sensitive_json=sensitive.model_dump_json(indent=2),
        surfaces="\n".join(surfaces) if surfaces else "(none yet)",
        visited="\n".join(visited) if visited else "(none yet)",
        history="\n".join(history) if history else "(none yet)",
        clickables=_format_clickables(snapshot),
    )
    data = _gemini_json(prompt, snapshot.screenshot_path)
    try:
        return BrowseDecision.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("browse decision validation failed: %s", exc)
        return BrowseDecision(action="finish", reason="parse_error")

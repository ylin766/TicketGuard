"""Real AuditFn: run the OSINT agent with a candidate prompt and return an
audit result the metric can score.

This is the piece that replaces the stub used while building the infra. It runs
the *actual* OSINT investigation under a GEPA candidate prompt, so each training
iteration measures the prompt being optimized.

The LLM/network-bound execution is isolated in :func:`run_osint_audit`; the
result-shaping and tool-success classification are pure helpers (``classify_tool_result``,
``assemble_audit``) so they stay unit-testable offline.

Tool-success note: a call that returns HTTP 403, a captcha/login wall, or an
empty body is counted as a *failure* even though it didn't raise — what matters
is whether the call yielded usable new information, not whether it technically
completed. The classifier below is a fast rule-based approximation; the design
leaves room to swap in an LLM judgment for training runs (where cost is fine).
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Substrings that mark a tool response as "no usable information", even on a
# technically successful call. Lower-cased before matching.
_FAILURE_MARKERS = (
    "exception",
    "failed",
    "error",
    "403",
    "forbidden",
    "captcha",
    "access denied",
    "rate limit",
    "timed out",
    "timeout",
    "no results",
    "not found",
)


def classify_tool_result(response: Any) -> bool:
    """Return True if a tool response carried usable new information.

    Treats empties and known failure/blocked markers as unsuccessful. Pure and
    deterministic so it's unit-testable; this is the rule-based approximation of
    the "did this call actually help?" question.
    """
    if response is None:
        return False
    text = str(response).strip()
    if not text:
        return False
    low = text.lower()
    if any(marker in low for marker in _FAILURE_MARKERS):
        return False
    return True


def assemble_audit(
    url: str,
    report: dict,
    *,
    tool_calls: int,
    tool_successes: int,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    duration_ms: int,
) -> dict:
    """Shape the OSINT run into the audit dict the metric/runner consume.

    The OSINT trust score (0–100) becomes the audit ``score`` (higher = safer),
    and tool stats go under ``agent_audit.stats`` exactly where
    ``metric.tool_success_rate`` reads them. Pure: no I/O."""
    return {
        "url": url,
        "score": report.get("score"),
        "risk_level": report.get("tier"),
        "agent_audit": {
            "report": report.get("text", ""),
            "stats": {
                "tool_calls": tool_calls,
                "tool_successes": tool_successes,
                "tool_failures": tool_calls - tool_successes,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "duration_ms": duration_ms,
            },
        },
    }


async def run_osint_audit(url: str, candidate: dict[str, str]) -> dict:
    """Run the OSINT agent on ``url`` using the candidate's prompt; return the
    audit dict. This is the real ``AuditFn`` for the training runner.

    Never raises for a single run — on failure it returns a zero-information
    audit (score=None) so the runner scores it as an abstention/failure rather
    than aborting the batch.
    """
    from .gepa_loop import OSINT_COMPONENT

    instruction = candidate.get(OSINT_COMPONENT)
    started = time.monotonic()

    try:
        from google.adk.runners import InMemoryRunner
        from google.genai import types as genai_types

        from ..features.security.agent.osint.subagent import make_osint_subagent
        from ..features.security.agent.osint_stream import _parse_report
    except Exception as exc:  # noqa: BLE001
        logger.warning("[audit] OSINT stack unavailable: %s", exc)
        return {"url": url, "score": None, "agent_audit": {"error": str(exc)}}

    agent = make_osint_subagent(instruction=instruction)
    tool_calls = 0
    tool_successes = 0
    prompt_tokens = completion_tokens = total_tokens = 0
    final_text = ""

    try:
        runner = InMemoryRunner(agent=agent, app_name="osint_train")
        session = await runner.session_service.create_session(
            app_name="osint_train", user_id="train"
        )
        user_msg = genai_types.Content(
            role="user",
            parts=[genai_types.Part(
                text=f"Investigate this ticketing website for fraud risk: {url}"
            )],
        )
        async for event in runner.run_async(
            user_id="train", session_id=session.id, new_message=user_msg
        ):
            usage = getattr(event, "usage_metadata", None)
            if usage is not None:
                prompt_tokens += getattr(usage, "prompt_token_count", 0) or 0
                completion_tokens += getattr(usage, "candidates_token_count", 0) or 0
                total_tokens += getattr(usage, "total_token_count", 0) or 0
            content = getattr(event, "content", None)
            if not content or not getattr(content, "parts", None):
                continue
            for part in content.parts:
                if getattr(part, "text", None):
                    final_text = part.text
                if getattr(part, "function_call", None):
                    tool_calls += 1
                fr = getattr(part, "function_response", None)
                if fr is not None:
                    if classify_tool_result(getattr(fr, "response", None)):
                        tool_successes += 1
    except Exception as exc:  # noqa: BLE001 - one audit must not abort training
        logger.warning("[audit] OSINT run failed for %s: %s", url, exc)
        return {"url": url, "score": None, "agent_audit": {"error": str(exc)}}

    report = _parse_report(final_text) if final_text else {"score": None, "tier": None, "text": ""}
    duration_ms = int((time.monotonic() - started) * 1000)
    return assemble_audit(
        url, report,
        tool_calls=tool_calls,
        tool_successes=tool_successes,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        duration_ms=duration_ms,
    )

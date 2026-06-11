"""Dual-agent security audit for training — the REAL system under optimization.

The production grey-zone gate (run the agent only when the deterministic
pipeline is uncertain) is deliberately BYPASSED here: for training/eval we always
run BOTH agents on every URL so the optimizer gets a signal on each example.

Two co-equal agents (NOT a fallback chain) run in parallel:

  * **Browser ReAct agent** — opens the page, explores sensitive surfaces; the
    deterministic rules then produce a 0–100 ``risk_score`` (higher = safer).
  * **OSINT agent** — web/social reputation search; emits a 0–100 trust score.

The final credibility score is their weighted blend (default 50/50):

    final = w_react · react_score + w_osint · osint_score

and the metric rewards ``final`` for converging to the dataset's *authoritative*
0–100 score (regression), not just for getting the safe/risky side right.

GEPA optimizes the two prompts as separate components (``react_prompt`` and
``osint_prompt``); both flow through here so a candidate for either agent is
measured by the same weighted-final objective.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

# GEPA component keys — the two prompts that can be optimized.
REACT_COMPONENT = "react_prompt"
OSINT_COMPONENT = "osint_prompt"

# Co-equal blend of the two agents' 0–100 scores (NOT a fallback). Tunable.
DEFAULT_AGENT_WEIGHTS: dict[str, float] = {"react": 0.5, "osint": 0.5}


def dual_seed_candidate() -> dict[str, str]:
    """The starting two-prompt candidate GEPA mutates: both production prompts."""
    from ..features.security.agent.browser_check.llm.prompts import (
        BROWSE_REACT_INSTRUCTION,
    )
    from ..features.security.agent.osint.prompt import OSINT_AGENT_PROMPT

    return {
        REACT_COMPONENT: BROWSE_REACT_INSTRUCTION,
        OSINT_COMPONENT: OSINT_AGENT_PROMPT,
    }


def blend_scores(
    react_score: float | None,
    osint_score: float | None,
    weights: dict[str, float] | None = None,
) -> float | None:
    """Weighted blend of the two 0–100 scores, renormalizing over what's present.

    Returns ``None`` only when BOTH agents failed to produce a score (a genuine
    abstention). If just one is missing, the other carries full weight.
    """
    weights = weights or DEFAULT_AGENT_WEIGHTS
    present: dict[str, float] = {}
    if react_score is not None:
        present["react"] = float(react_score)
    if osint_score is not None:
        present["osint"] = float(osint_score)
    if not present:
        return None
    total_w = sum(weights.get(k, 0.0) for k in present)
    if total_w <= 0:
        return sum(present.values()) / len(present)
    return sum(weights.get(k, 0.0) * v for k, v in present.items()) / total_w


async def _run_react(url: str, react_instruction: str | None) -> dict:
    """Run the browser ReAct agent only (OSINT disabled); never raises."""
    try:
        from ..features.security.agent.browser_check.browser_security_tool import (
            browser_security_check,
        )

        result = await browser_security_check(
            url,
            enable_osint=False,            # OSINT runs separately, co-equal
            headless=True,
            react_instruction=react_instruction,
        )
        return result if isinstance(result, dict) else {}
    except Exception as exc:  # noqa: BLE001 - one agent failing must not abort
        logger.warning("[dual] browser ReAct failed for %s: %s", url, exc)
        return {"error": str(exc)}


async def _run_osint(url: str, osint_instruction: str | None) -> dict:
    """Run the OSINT reputation agent only; never raises."""
    from .audit_fn import run_osint_audit
    from .gepa_loop import OSINT_COMPONENT as _OSINT_KEY

    try:
        return await run_osint_audit(url, {_OSINT_KEY: osint_instruction})
    except Exception as exc:  # noqa: BLE001
        logger.warning("[dual] OSINT failed for %s: %s", url, exc)
        return {"score": None, "agent_audit": {"error": str(exc)}}


def _react_tool_stats(react: dict) -> tuple[int, int]:
    """Best-effort (calls, successes) from a browser result's transitions."""
    transitions = react.get("transitions")
    if isinstance(transitions, list) and transitions:
        calls = len(transitions)
        # A transition that recorded a stopped_reason error counts as a failure.
        successes = sum(
            1 for t in transitions
            if isinstance(t, dict) and not t.get("stopped_reason")
        )
        return calls, successes
    return 0, 0


async def run_security_dual_audit(
    url: str,
    candidate: dict[str, str],
    *,
    weights: dict[str, float] | None = None,
) -> dict:
    """Run BOTH agents on ``url`` in parallel and return a blended audit dict.

    ``candidate`` may carry ``react_prompt`` and/or ``osint_prompt`` overrides
    (GEPA's components). The returned ``score`` is the weighted blend the metric
    compares against the authoritative score; ``react_score`` / ``osint_score``
    are kept for transparency.
    """
    started = time.monotonic()
    react_instruction = candidate.get(REACT_COMPONENT)
    osint_instruction = candidate.get(OSINT_COMPONENT)

    # SERIAL on purpose: running both agents concurrently spikes Vertex
    # concurrency and trips 429 RESOURCE_EXHAUSTED. The two are co-equal in the
    # scoring blend regardless of run order.
    react = await _run_react(url, react_instruction)
    osint = await _run_osint(url, osint_instruction)

    react_score = react.get("risk_score")
    osint_score = osint.get("score")
    final = blend_scores(react_score, osint_score, weights)

    react_calls, react_succ = _react_tool_stats(react)
    osint_stats = (osint.get("agent_audit") or {}).get("stats") or {}
    tool_calls = react_calls + int(osint_stats.get("tool_calls", 0) or 0)
    tool_successes = react_succ + int(osint_stats.get("tool_successes", 0) or 0)
    total_tokens = int(osint_stats.get("total_tokens", 0) or 0)

    return {
        "url": url,
        "score": final,
        "react_score": react_score,
        "osint_score": osint_score,
        "weights": weights or DEFAULT_AGENT_WEIGHTS,
        "agent_audit": {
            "react_verdict": react.get("verdict"),
            "react_summary": react.get("summary"),
            "osint_tier": (osint.get("agent_audit") or {}).get("tier"),
            "stats": {
                "tool_calls": tool_calls,
                "tool_successes": tool_successes,
                "total_tokens": total_tokens,
            },
        },
        "latency_ms": int((time.monotonic() - started) * 1000),
    }

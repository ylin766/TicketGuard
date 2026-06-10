"""Security orchestrator — the whole security workflow.

    url
     |
     v
  run_pipeline(url)            # deterministic threat-intel, no LLM
     |
     v
  scoring → credibility score (0-100) + risk band
     |
     v
  grey zone?
     · score < GREY_ZONE_DANGER_MAX → conclusive DANGEROUS  → no agent
     · score >= GREY_ZONE_SAFE_MIN  → conclusive SAFE        → no agent
     · in between (or pipeline down) → uncertain → run the agent
     |
     v (only in the grey zone)
  browser_security_check(url)  # ReAct browser exploration + OSINT
     |
     v
  enriched result (findings + score + grey_zone + agent_audit)

The reusable flow lives in :func:`run_security_audit`; the ADK
``SecurityOrchestrator`` is a thin wrapper that runs it and writes the result to
session state, and the HTTP layer can call the same function directly.
"""

import asyncio
import logging
import time
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from typing_extensions import override

from ...core.state_keys import PAGE_URL, SECURITY_RESULT
from .pipeline import run_pipeline
from .scoring import generate_score_breakdown

logger = logging.getLogger(__name__)

# Grey-zone band on the credibility score (0-100, higher = safer):
#   below DANGER_MAX → conclusively dangerous (multi-source consensus), judge it
#                      directly without spending the agent;
#   at/above SAFE_MIN → conclusively safe, the agent would add nothing;
#   in between        → uncertain, escalate to the agent.
GREY_ZONE_DANGER_MAX = 20
GREY_ZONE_SAFE_MIN = 95


def is_grey_zone(pipeline_result: dict, score: int) -> bool:
    """Whether the pipeline is INconclusive and the agent should investigate.

    An unavailable pipeline always escalates (we genuinely can't tell). Otherwise
    only the uncertain middle band escalates: a very low score is a confident
    multi-signal danger verdict, and a high score is a confident pass — neither
    needs the slower, more expensive agent audit.
    """
    if not pipeline_result or pipeline_result.get("status") == "unavailable":
        return True
    return GREY_ZONE_DANGER_MAX <= score < GREY_ZONE_SAFE_MIN


async def _run_agent_audit(url: str) -> dict:
    """Run the browser + OSINT agent audit on ``url``; never raises.

    ``browser_security_check`` is the full agent stage: a ReAct browser explorer
    plus, for non-whitelisted sites, an OSINT reputation check — one combined
    result dict.
    """
    try:
        from .agent.browser_check.browser_security_tool import browser_security_check

        audit = await browser_security_check(url)
        logger.info("agent audit verdict=%s risk=%s",
                    audit.get("verdict"), audit.get("risk_level"))
        return audit
    except Exception as exc:  # noqa: BLE001 - the audit must never crash the run
        logger.exception("agent audit failed: %s", exc)
        return {"status": "error", "error": str(exc)}


def _agent_token_total(agent_audit: dict | None) -> int | None:
    """Best-effort extraction of the agent stage's token spend, for the cost
    attribute on the trace. Tolerates the field being absent or differently
    shaped — returns ``None`` when nothing usable is found."""
    if not isinstance(agent_audit, dict):
        return None
    stats = agent_audit.get("stats")
    if isinstance(stats, dict) and stats.get("total_tokens") is not None:
        return stats.get("total_tokens")
    if agent_audit.get("total_tokens") is not None:
        return agent_audit.get("total_tokens")
    return None


async def run_security_audit(url: str, run_id: str | None = None) -> dict:
    """Full security audit for ``url`` — the single reusable entry point.

    Runs the deterministic pipeline, synthesizes the score, and (only in the grey
    zone) escalates to the browser+OSINT agent. Returns the pipeline result
    enriched with ``score`` / ``risk_level`` / ``score_explanation`` /
    ``grey_zone`` / ``run_id`` and, when the agent ran, ``agent_audit``.

    ``run_id`` is the correlation key that ties this audit's Phoenix trace to any
    reward later attached to it; one is generated when the caller doesn't supply
    one. The whole audit runs inside a root span so every instrumented child
    span (pipeline, ADK agent, genai) nests under a single, queryable trace.
    """
    from ...observability.trace_utils import (
        audit_span,
        new_run_id,
        set_audit_result,
    )

    run_id = run_id or new_run_id()
    started = time.monotonic()

    with audit_span(url, run_id) as span:
        pipeline_result = await asyncio.to_thread(run_pipeline, url)

        breakdown = generate_score_breakdown(pipeline_result)
        pipeline_result["score"] = breakdown["score"]
        pipeline_result["risk_level"] = breakdown["risk_level"]
        pipeline_result["score_explanation"] = breakdown["explanation"]

        grey = is_grey_zone(pipeline_result, breakdown["score"])
        pipeline_result["grey_zone"] = grey
        pipeline_result["run_id"] = run_id
        logger.info("run_id=%s score=%s flagged=%s grey_zone=%s",
                    run_id, breakdown["score"], pipeline_result.get("flagged"), grey)

        agent_ran = bool(grey and url)
        if agent_ran:
            pipeline_result["agent_audit"] = await _run_agent_audit(url)

        # Deep-link to the Phoenix trace for this audit's agent activity, if
        # tracing is enabled (telemetry is bootstrapped centrally at startup).
        try:
            from ...observability.telemetry import phoenix_url

            pipeline_result["phoenix_url"] = phoenix_url()
        except Exception:  # noqa: BLE001 - never let telemetry lookup break the audit
            pipeline_result["phoenix_url"] = None

        # Record the decision + cost attributes on the root span: this is the
        # (state, action, cost) record a reward signal later binds to.
        set_audit_result(
            span,
            score=breakdown["score"],
            risk_level=breakdown["risk_level"],
            grey_zone=grey,
            agent_ran=agent_ran,
            flagged=pipeline_result.get("flagged"),
            status=pipeline_result.get("status"),
            latency_ms=int((time.monotonic() - started) * 1000),
            agent_tokens=_agent_token_total(pipeline_result.get("agent_audit")),
        )

    return pipeline_result


class SecurityOrchestrator(BaseAgent):
    """ADK wrapper: run the audit, write the enriched result to session state."""

    def __init__(self, name: str):
        super().__init__(name=name)

    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        url = ctx.session.state.get(PAGE_URL, "")
        result = await run_security_audit(url)
        # A custom agent must emit state via a state_delta event — direct
        # ``ctx.session.state[...] = ...`` writes are not committed by the runner.
        yield Event(
            author=self.name,
            actions=EventActions(state_delta={SECURITY_RESULT: result}),
        )


security_orchestrator = SecurityOrchestrator(name="security_orchestrator")

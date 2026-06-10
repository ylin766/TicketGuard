"""Trace helpers for the RL data layer on top of Arize Phoenix.

``telemetry.py`` bootstraps the exporter + OpenInference instrumentors; this
module is the *business-semantic* layer on top of those auto-generated LLM
spans. Its single job is to make every security audit emit one **root span**
carrying a stable ``run_id`` plus the decision/cost attributes we later need to
attach rewards to.

Why this matters: the OpenInference instrumentors already capture the raw LLM
spans (tokens, prompts, tool calls), but those are anonymous and unlinked. By
opening one root span per audit we (a) group all child spans into a single
trace, and (b) record the agent's *action* (score, grey-zone routing) and the
*cost* (latency, tokens). That turns each Phoenix trace into a
``(state, action, cost)`` record — the substrate a reward signal binds to.

Everything here is best-effort: if tracing is disabled or the OTel SDK is
absent, the helpers degrade to no-ops and never raise on the request path.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger(__name__)

# Attribute namespace for TicketGuard-specific fields. Keep these stable: the
# offline trainer / dataset builder filters and reads traces by these keys.
ATTR_RUN_ID = "ticketguard.run_id"
ATTR_SCORE = "ticketguard.score"
ATTR_RISK_LEVEL = "ticketguard.risk_level"
ATTR_GREY_ZONE = "ticketguard.grey_zone"
ATTR_AGENT_RAN = "ticketguard.agent_ran"
ATTR_FLAGGED = "ticketguard.flagged"
ATTR_STATUS = "ticketguard.status"
ATTR_LATENCY_MS = "ticketguard.latency_ms"
ATTR_AGENT_TOKENS = "ticketguard.agent_tokens"

# OpenInference / Phoenix standard span attributes (so the UI renders the
# input URL and the output verdict natively).
ATTR_INPUT_VALUE = "input.value"
ATTR_OUTPUT_VALUE = "output.value"

_TRACER_NAME = "ticketguard.audit"


def new_run_id() -> str:
    """A fresh correlation id for one audit, used as the reward-binding key."""
    return uuid.uuid4().hex


def _get_tracer():
    """Return an OTel tracer, or ``None`` when the SDK isn't installed."""
    try:
        from opentelemetry import trace as _trace

        return _trace.get_tracer(_TRACER_NAME)
    except Exception:  # noqa: BLE001 - tracing must never break the request path
        return None


def _safe_set(span, key: str, value) -> None:
    """Set one span attribute, swallowing any error and skipping ``None``."""
    if value is None:
        return
    try:
        span.set_attribute(key, value)
    except Exception:  # noqa: BLE001
        pass


@contextmanager
def audit_span(url: str, run_id: str) -> Iterator[object | None]:
    """Open the root span for one security audit.

    Yields the live span (so the caller can attach result attributes once the
    audit is done) or ``None`` when tracing is unavailable. All child spans
    produced by the instrumentors during the ``with`` block are nested under
    this span, giving one trace per audit keyed by ``run_id``.
    """
    tracer = _get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span("ticketguard.security_audit") as span:
        _safe_set(span, ATTR_RUN_ID, run_id)
        _safe_set(span, ATTR_INPUT_VALUE, url)
        yield span


def set_audit_result(
    span,
    *,
    score: int | None = None,
    risk_level: str | None = None,
    grey_zone: bool | None = None,
    agent_ran: bool | None = None,
    flagged: bool | None = None,
    status: str | None = None,
    latency_ms: int | None = None,
    agent_tokens: int | None = None,
) -> None:
    """Attach the audit's decision + cost attributes to its root span.

    No-op when ``span`` is ``None`` (tracing disabled). Every field is optional
    so partial results (e.g. a pipeline-only run with no agent) still record
    whatever is known.
    """
    if span is None:
        return
    _safe_set(span, ATTR_SCORE, score)
    _safe_set(span, ATTR_RISK_LEVEL, risk_level)
    _safe_set(span, ATTR_GREY_ZONE, grey_zone)
    _safe_set(span, ATTR_AGENT_RAN, agent_ran)
    _safe_set(span, ATTR_FLAGGED, flagged)
    _safe_set(span, ATTR_STATUS, status)
    _safe_set(span, ATTR_LATENCY_MS, latency_ms)
    _safe_set(span, ATTR_AGENT_TOKENS, agent_tokens)
    if score is not None:
        verdict = f"score={score}"
        if risk_level:
            verdict += f" risk={risk_level}"
        _safe_set(span, ATTR_OUTPUT_VALUE, verdict)

"""LLM-as-judge reward channel — built on Phoenix's own ``phoenix.evals``.

This is the *reward* half of the RL data loop. ``trace_utils`` records each audit
as a ``(state, action, cost)`` trace; this module scores that trace so the triple
becomes ``(state, action, reward)`` — the substrate offline training (and GEPA's
reflective prompt evolution) consumes.

We deliberately reuse the sponsor's library rather than hand-rolling a judge:
``phoenix.evals.create_classifier`` gives us structured, enum-constrained output
(via tool calling), built-in rate-limit/retry executors, and native Phoenix
integration — the same evaluators can be passed straight to
``px_client.experiments.run_experiment(evaluators=[...])`` and used as a GEPA
metric.

Three orthogonal rubrics, each mapping an enum label to a 0–1 reward component:

* ``evidence_grounding``  — is the verdict supported by the collected evidence?
                            (the anti-hallucination term)
* ``consistency``         — do score, risk band, and agent report agree?
* ``routing_efficiency``  — was spending (or not spending) the agent justified?
                            (the cost term, feeding the grey-zone policy)

Everything is best-effort: if ``phoenix.evals`` or a judge LLM is unavailable,
the judge degrades to an empty result and never raises on the caller's path.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Default judge model — a cheap, fast model is enough for grading and keeps the
# dense reward signal affordable. Honors the project's Vertex routing via the
# GOOGLE_GENAI_USE_VERTEXAI env var picked up by the google-genai client.
_DEFAULT_JUDGE_MODEL = "gemini-2.5-flash"
_JUDGE_PROVIDER = "google"

# Enum label → reward component (0–1). Kept module-level so training code and the
# aggregate reward share one source of truth.
GROUNDING_CHOICES: dict[str, float] = {
    "grounded": 1.0,
    "partially_grounded": 0.5,
    "ungrounded": 0.0,
}
CONSISTENCY_CHOICES: dict[str, float] = {
    "consistent": 1.0,
    "minor_inconsistency": 0.5,
    "contradictory": 0.0,
}
EFFICIENCY_CHOICES: dict[str, float] = {
    "appropriate": 1.0,
    "wasteful": 0.3,
    "missed_escalation": 0.0,
}

# Weights for collapsing the three components into one scalar reward. Grounding
# dominates (correctness matters most); efficiency is the cost discount.
REWARD_WEIGHTS: dict[str, float] = {
    "evidence_grounding": 0.5,
    "consistency": 0.3,
    "routing_efficiency": 0.2,
}

_GROUNDING_TEMPLATE = """\
You are auditing a ticket-fraud risk assessment. Decide whether the final verdict
is supported by the evidence that was actually collected — not by outside
knowledge.

URL: {{url}}
Final score (0=dangerous, 100=safe): {{score}}
Risk level: {{risk_level}}

Collected threat-intel evidence:
{{evidence}}

Agent investigation report (may be empty if no agent ran):
{{agent_report}}

Respond:
- "grounded" if the verdict clearly follows from the evidence.
- "partially_grounded" if partly supported but overreaching or ignoring signals.
- "ungrounded" if the verdict is not supported by the evidence (hallucinated)."""

_CONSISTENCY_TEMPLATE = """\
You are auditing a ticket-fraud risk assessment for internal consistency.
Check whether the numeric score, the risk-level label, and the agent report all
agree with each other.

Final score (0=dangerous, 100=safe): {{score}}
Risk level: {{risk_level}}
Agent investigation report (may be empty):
{{agent_report}}

Respond:
- "consistent" if score, risk level, and report tell the same story.
- "minor_inconsistency" if mostly aligned with small tension.
- "contradictory" if they materially disagree (e.g. fraud evidence but safe score)."""

_EFFICIENCY_TEMPLATE = """\
You are auditing whether a fraud-detection pipeline spent its expensive agent
stage wisely. The pipeline runs a deterministic threat-intel scan, then only
escalates to a slow browser+OSINT agent when the result is uncertain ("grey
zone").

Final score (0=dangerous, 100=safe): {{score}}
Was the grey-zone reached: {{grey_zone}}
Did the agent actually run: {{agent_ran}}

Collected threat-intel evidence:
{{evidence}}

Respond:
- "appropriate" if running (or skipping) the agent matched the uncertainty.
- "wasteful" if the agent ran although the scan was already conclusive.
- "missed_escalation" if the agent should have run on uncertain evidence but didn't."""

_EVALUATOR_SPECS = (
    ("evidence_grounding", _GROUNDING_TEMPLATE, GROUNDING_CHOICES),
    ("consistency", _CONSISTENCY_TEMPLATE, CONSISTENCY_CHOICES),
    ("routing_efficiency", _EFFICIENCY_TEMPLATE, EFFICIENCY_CHOICES),
)

_PREVIEW_LIMIT = 4000


def summarize_evidence(pipeline_result: dict | None) -> str:
    """Flatten the pipeline's per-source findings into a compact text block the
    judge can read. Tolerates any field being missing — only includes sources
    that actually returned something."""
    if not isinstance(pipeline_result, dict):
        return "(no evidence available)"

    lines: list[str] = []
    sources = pipeline_result.get("sources")
    if isinstance(sources, list):
        for src in sources:
            if not isinstance(src, dict):
                continue
            name = src.get("name") or src.get("source") or "source"
            threat = src.get("threat")
            detail = src.get("detail") or src.get("description") or ""
            flag = "THREAT" if threat else ("clean" if threat is False else "?")
            lines.append(f"- {name}: {flag} {detail}".rstrip())

    if not lines:
        # Fall back to top-level signals so the judge isn't left blank.
        for key in ("flagged", "status", "score_explanation"):
            val = pipeline_result.get(key)
            if val is not None:
                lines.append(f"- {key}: {val}")

    text = "\n".join(lines) if lines else "(no evidence available)"
    return text[:_PREVIEW_LIMIT]


def _agent_report_text(result: dict) -> str:
    """Best-effort extraction of the agent stage's narrative report."""
    audit = result.get("agent_audit")
    if not isinstance(audit, dict):
        return "(no agent report)"
    for key in ("report", "report_text", "summary", "text", "verdict"):
        val = audit.get(key)
        if isinstance(val, str) and val.strip():
            return val[:_PREVIEW_LIMIT]
    return "(no agent report)"


def build_snapshot(result: dict) -> dict[str, Any]:
    """Build the immutable judging input from an audit result dict.

    Pure and offline: just rearranges fields the orchestrator already produced
    into the variables the rubric templates reference. Keeping it deterministic
    is what makes the judge reproducible across runs."""
    return {
        "run_id": result.get("run_id", ""),
        "url": result.get("url") or result.get("input") or "",
        "score": result.get("score"),
        "risk_level": result.get("risk_level") or "",
        "grey_zone": bool(result.get("grey_zone")),
        "agent_ran": isinstance(result.get("agent_audit"), dict),
        "evidence": summarize_evidence(result),
        "agent_report": _agent_report_text(result),
    }


_llm_cache: Any | None = None


def get_judge_llm(model: str | None = None) -> Any | None:
    """Construct (and cache) the judge LLM via phoenix.evals. Returns ``None``
    when the library or a provider is unavailable, so callers degrade quietly."""
    global _llm_cache
    if _llm_cache is not None:
        return _llm_cache
    try:
        from phoenix.evals import LLM

        _llm_cache = LLM(
            provider=_JUDGE_PROVIDER,
            model=model or os.environ.get("GEMINI_MODEL", _DEFAULT_JUDGE_MODEL),
        )
    except Exception as exc:  # noqa: BLE001 - judge must never break the caller
        logger.warning("[judge] judge LLM unavailable: %s", exc)
        _llm_cache = None
    return _llm_cache


def build_evaluators(llm: Any | None = None) -> list[Any]:
    """Create the three Phoenix ClassificationEvaluators. Returns ``[]`` when the
    evals library or judge LLM isn't available. The returned evaluators are also
    directly usable as ``run_experiment(evaluators=...)`` or a GEPA metric."""
    llm = llm or get_judge_llm()
    if llm is None:
        return []
    try:
        from phoenix.evals import create_classifier
    except Exception as exc:  # noqa: BLE001
        logger.warning("[judge] phoenix.evals unavailable: %s", exc)
        return []

    evaluators: list[Any] = []
    for name, template, choices in _EVALUATOR_SPECS:
        try:
            evaluators.append(
                create_classifier(
                    name=name,
                    prompt_template=template,
                    llm=llm,
                    choices=choices,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[judge] failed to build evaluator %s: %s", name, exc)
    return evaluators


def judge_audit(result: dict, evaluators: list[Any] | None = None) -> dict[str, dict]:
    """Score one audit result with the LLM judge.

    Returns ``{dimension: {"score": float|None, "label": str|None,
    "explanation": str|None}}``. Best-effort: returns ``{}`` when judging is
    unavailable, and skips any single dimension that errors. ``evaluators`` can
    be injected (e.g. in tests) to avoid building/calling real LLMs.
    """
    evaluators = evaluators if evaluators is not None else build_evaluators()
    if not evaluators:
        return {}

    snapshot = build_snapshot(result)
    out: dict[str, dict] = {}
    for evaluator in evaluators:
        name = getattr(evaluator, "name", "eval")
        try:
            scores = evaluator.evaluate(snapshot)
            if not scores:
                continue
            score = scores[0]
            out[name] = {
                "score": getattr(score, "score", None),
                "label": getattr(score, "label", None),
                "explanation": getattr(score, "explanation", None),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("[judge] evaluator %s failed: %s", name, exc)
    return out


def aggregate_reward(judged: dict[str, dict], weights: dict[str, float] | None = None) -> float | None:
    """Collapse the per-dimension judge scores into one scalar reward in [0,1].

    Uses ``REWARD_WEIGHTS`` over whichever dimensions are present (renormalized),
    so a partial judge result still yields a usable reward. Returns ``None`` when
    nothing scorable is present — never invent a reward from no signal.
    """
    weights = weights or REWARD_WEIGHTS
    total_w = 0.0
    acc = 0.0
    for dim, payload in judged.items():
        if not isinstance(payload, dict):
            continue
        s = payload.get("score")
        w = weights.get(dim)
        if s is None or w is None:
            continue
        acc += w * float(s)
        total_w += w
    if total_w == 0.0:
        return None
    return acc / total_w

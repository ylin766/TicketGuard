"""GEPA-compatible evaluation metric for one audit.

GEPA optimizes a system against *any* metric that, given a candidate's output
on a dataset example, returns a scalar score — and, crucially, can also return
**Actionable Side Information (ASI)**: natural-language diagnostics the
reflection LLM reads to propose better prompts. This module produces both.

The metric blends three signals (weights tunable):

  1. ``correctness``  — does the system's verdict match the ground-truth label?
                        Objective, the hardest signal. The 0–100 score is
                        thresholded into safe/risky; the threshold itself is a
                        parameter (so it can be tuned as part of object-1).
  2. ``tool_success`` — fraction of the agent's tool calls that succeeded.
                        Objective; rewards an agent that uses tools reliably.
  3. ``judge``        — the LLM-as-judge reward (grounding / consistency /
                        efficiency) from ``observability.judge``. Softer signal,
                        gated behind human-calibrated trust.

Everything is offline-friendly and dependency-light: the judge degrades to a
neutral contribution when unavailable, and tool stats default to "unknown"
rather than erroring, so the metric still runs on a bare audit result.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Score (0=dangerous .. 100=safe) at/above which a URL is predicted "safe".
# Below it, "risky". This is object-1's learnable decision threshold; exposed so
# the trainer can tune it rather than hard-coding 50.
DEFAULT_SAFE_THRESHOLD = 50

# Blend weights over the three signals. Correctness dominates (it's ground
# truth); judge is the smallest because it's the least trusted.
DEFAULT_METRIC_WEIGHTS: dict[str, float] = {
    "correctness": 0.6,
    "tool_success": 0.2,
    "judge": 0.2,
}


@dataclass
class MetricResult:
    """Outcome of scoring one audit against its ground-truth label.

    ``score`` is the scalar GEPA maximizes (0..1). ``feedback`` is the ASI:
    human-readable diagnostics the reflective optimizer learns from.
    """

    score: float
    correct: bool | None
    predicted_label: str | None
    components: dict[str, float | None] = field(default_factory=dict)
    feedback: str = ""

    def as_gepa(self) -> dict[str, Any]:
        """Shape GEPA expects from a metric: a scalar plus side-info text."""
        return {"score": self.score, "feedback": self.feedback}


def predict_label(score: int | float | None, threshold: int = DEFAULT_SAFE_THRESHOLD) -> str | None:
    """Threshold a 0–100 credibility score into ``safe`` / ``risky``.

    Returns ``None`` when no score is available (pipeline unavailable), so the
    caller can treat it as an abstention rather than a wrong guess.
    """
    if score is None:
        return None
    return "safe" if float(score) >= threshold else "risky"


def tool_success_rate(audit: dict | None) -> float | None:
    """Fraction of agent tool calls that succeeded, or ``None`` if unknown.

    Reads the OSINT/agent stage stats already collected during a run. Tolerant
    of several shapes; returns ``None`` (not 0) when there's no tool activity to
    judge, so a no-agent audit doesn't get falsely penalised.
    """
    if not isinstance(audit, dict):
        return None
    stats = audit.get("stats") if isinstance(audit.get("stats"), dict) else audit
    total = stats.get("tool_calls")
    failed = stats.get("tool_failures")
    succeeded = stats.get("tool_successes")
    if isinstance(total, int) and total > 0:
        if isinstance(succeeded, int):
            return max(0.0, min(1.0, succeeded / total))
        if isinstance(failed, int):
            return max(0.0, min(1.0, (total - failed) / total))
    return None


def _correctness_feedback(predicted: str | None, truth: str, score: Any) -> str:
    if predicted is None:
        return f"ABSTAINED: no score produced; ground truth was '{truth}'."
    if predicted == truth:
        return f"CORRECT: predicted '{predicted}' (score={score}) == truth '{truth}'."
    return (
        f"WRONG: predicted '{predicted}' (score={score}) but truth is '{truth}'. "
        f"{'Missed a risky site (false safe).' if truth == 'risky' else 'Flagged a safe site (false alarm).'}"
    )


def score_audit(
    audit: dict,
    truth_label: str,
    *,
    threshold: int = DEFAULT_SAFE_THRESHOLD,
    weights: dict[str, float] | None = None,
    judged: dict[str, dict] | None = None,
) -> MetricResult:
    """Score one audit result against its ground-truth label.

    Args:
        audit: the audit result dict (``score``, ``agent_audit``/``stats``, …).
        truth_label: ``"safe"`` or ``"risky"`` from the dataset.
        threshold: safe/risky decision boundary on the 0–100 score.
        weights: blend weights over correctness / tool_success / judge.
        judged: precomputed judge output (from ``judge.judge_audit``); if given,
            its aggregate reward feeds the ``judge`` component. Passing it in
            keeps this function offline and unit-testable.

    Returns a :class:`MetricResult` with the scalar GEPA maximizes and ASI text.
    """
    weights = weights or DEFAULT_METRIC_WEIGHTS
    raw_score = audit.get("score")
    predicted = predict_label(raw_score, threshold)
    correct = None if predicted is None else (predicted == truth_label)

    # --- component 1: correctness (objective) ---
    correctness_val = 1.0 if correct else 0.0
    feedback_parts = [_correctness_feedback(predicted, truth_label, raw_score)]

    # --- component 2: tool success (objective) ---
    tsr = tool_success_rate(audit.get("agent_audit"))
    if tsr is not None:
        feedback_parts.append(f"Tool success rate: {tsr:.0%}.")

    # --- component 3: judge reward (soft) ---
    judge_val: float | None = None
    if judged is not None:
        from ..observability.judge import aggregate_reward

        judge_val = aggregate_reward(judged)
        if judge_val is not None:
            feedback_parts.append(f"Judge reward: {judge_val:.2f}.")
        for dim, payload in judged.items():
            expl = (payload or {}).get("explanation")
            if expl:
                feedback_parts.append(f"[{dim}] {expl}")

    # --- blend present components, renormalizing over what's available ---
    present: dict[str, float] = {"correctness": correctness_val}
    if tsr is not None:
        present["tool_success"] = tsr
    if judge_val is not None:
        present["judge"] = judge_val

    total_w = sum(weights.get(k, 0.0) for k in present)
    blended = (
        sum(weights.get(k, 0.0) * v for k, v in present.items()) / total_w
        if total_w > 0
        else correctness_val
    )

    return MetricResult(
        score=round(blended, 4),
        correct=correct,
        predicted_label=predicted,
        components={
            "correctness": correctness_val,
            "tool_success": tsr,
            "judge": judge_val,
        },
        feedback=" ".join(feedback_parts),
    )


# Blend weights for agents WITHOUT ground truth (price, seat): there is no
# correctness term, so reward rests on the LLM judge plus tool reliability.
DEFAULT_JUDGE_ONLY_WEIGHTS: dict[str, float] = {
    "judge": 0.8,
    "tool_success": 0.2,
}


def score_judge_only(
    audit: dict,
    judged: dict[str, dict],
    *,
    weights: dict[str, float] | None = None,
) -> MetricResult:
    """Score an audit that has NO ground-truth label (price / seat).

    Reward comes from the LLM judge (grounding/consistency/usefulness) plus the
    objective tool-success rate — never from a correctness comparison, since
    there is no truth to compare against. ``correct``/``predicted_label`` stay
    ``None`` so aggregation treats these as unscored-for-accuracy.
    """
    weights = weights or DEFAULT_JUDGE_ONLY_WEIGHTS
    feedback_parts: list[str] = []

    # Average the judge dimensions directly (equal weight) — price/seat have
    # their own rubric dimension names, so we don't route through the
    # security-keyed REWARD_WEIGHTS here.
    dim_scores = [
        float(p["score"])
        for p in (judged or {}).values()
        if isinstance(p, dict) and p.get("score") is not None
    ]
    judge_val = (sum(dim_scores) / len(dim_scores)) if dim_scores else None
    if judge_val is not None:
        feedback_parts.append(f"Judge reward: {judge_val:.2f}.")
    for dim, payload in (judged or {}).items():
        expl = (payload or {}).get("explanation")
        if expl:
            feedback_parts.append(f"[{dim}] {expl}")

    tsr = tool_success_rate(audit.get("agent_audit"))
    if tsr is not None:
        feedback_parts.append(f"Tool success rate: {tsr:.0%}.")

    present: dict[str, float] = {}
    if judge_val is not None:
        present["judge"] = judge_val
    if tsr is not None:
        present["tool_success"] = tsr

    total_w = sum(weights.get(k, 0.0) for k in present)
    blended = (
        sum(weights.get(k, 0.0) * v for k, v in present.items()) / total_w
        if total_w > 0
        else 0.0
    )

    return MetricResult(
        score=round(blended, 4),
        correct=None,
        predicted_label=None,
        components={"judge": judge_val, "tool_success": tsr},
        feedback=" ".join(feedback_parts) or "No judge/tool signal available.",
    )


def score_regression(
    audit: dict,
    authoritative_score: int | float,
    *,
    threshold: int = DEFAULT_SAFE_THRESHOLD,
) -> MetricResult:
    """Score a dual-agent audit by how close its blended 0–100 score lands to the
    dataset's AUTHORITATIVE 0–100 score (regression, not classification).

        reward = 1 - |final - authoritative| / 100        (clamped to [0, 1])

    A binary correctness flag (both sides of ``threshold``) is also recorded for
    a human-readable accuracy line, but the optimizer maximizes the smooth reward
    so it gets gradient even when the predicted side is already right.
    """
    final = audit.get("score")
    auth = float(authoritative_score)
    truth_label = "safe" if auth >= threshold else "risky"

    if final is None:
        return MetricResult(
            score=0.0,
            correct=False,
            predicted_label=None,
            components={"final": None, "authoritative": auth, "abs_error": None,
                        "tool_success": tool_success_rate(audit.get("agent_audit"))},
            feedback=(f"ABSTAINED: no blended score produced; authoritative "
                      f"score was {auth:.0f} ('{truth_label}')."),
        )

    final_f = float(final)
    abs_err = abs(final_f - auth)
    reward = max(0.0, 1.0 - abs_err / 100.0)
    predicted = predict_label(final_f, threshold)
    correct = predicted == truth_label

    react = audit.get("react_score")
    osint = audit.get("osint_score")
    tsr = tool_success_rate(audit.get("agent_audit"))

    direction = ""
    if abs_err > 0:
        if final_f > auth:
            direction = (f" Push the credibility score DOWN toward {auth:.0f} "
                         "(treat this site as LESS trustworthy / more scam-like).")
        else:
            direction = (f" Push the credibility score UP toward {auth:.0f} "
                         "(treat this site as MORE trustworthy / less scam-like).")
    else:
        direction = " On target."
    feedback = (
        "SCALE: 0-100 CREDIBILITY where HIGHER = SAFER / more trustworthy and "
        "LOWER = more likely a scam (this is NOT a risk score). "
        f"{'CORRECT' if correct else 'WRONG SIDE'}: blended final={final_f:.0f} "
        f"(react={react}, osint={osint}) vs authoritative={auth:.0f} "
        f"['{truth_label}']. Absolute error {abs_err:.0f}/100 -> reward {reward:.2f}."
        + direction
    )

    return MetricResult(
        score=round(reward, 4),
        correct=correct,
        predicted_label=predicted,
        components={
            "final": final_f,
            "react": react,
            "osint": osint,
            "authoritative": auth,
            "abs_error": abs_err,
            "tool_success": tsr,
        },
        feedback=feedback,
    )


def aggregate_metrics(results: list[MetricResult]) -> dict[str, float]:
    """Summarize a batch of per-example results into dataset-level numbers the
    learning curve plots: mean reward, accuracy, and mean tool success."""
    if not results:
        return {"mean_score": 0.0, "accuracy": 0.0, "n": 0}
    scored = [r.score for r in results]
    judged_correct = [r for r in results if r.correct is not None]
    accuracy = (
        sum(1 for r in judged_correct if r.correct) / len(judged_correct)
        if judged_correct
        else 0.0
    )
    tsrs = [r.components.get("tool_success") for r in results]
    tsrs = [t for t in tsrs if t is not None]
    summary = {
        "mean_score": round(sum(scored) / len(scored), 4),
        "accuracy": round(accuracy, 4),
        "mean_tool_success": round(sum(tsrs) / len(tsrs), 4) if tsrs else None,
        "n": len(results),
        "n_scored": len(judged_correct),
    }
    # Regression runs (dual-agent vs authoritative score) carry an abs-error; if
    # present, surface the mean absolute error (0–100) on the summary too.
    abs_errs = [
        r.components.get("abs_error")
        for r in results
        if r.components.get("abs_error") is not None
    ]
    if abs_errs:
        summary["mean_abs_error"] = round(sum(abs_errs) / len(abs_errs), 2)
    return summary

"""Batch runner: execute the audit over a dataset split and score each result.

This is the bridge between the dataset/metric and the GEPA optimizer. It is
deliberately *injectable*: the thing that turns a (candidate, url) into an audit
result is a pluggable ``AuditFn``, so the infrastructure can be exercised with a
stub before the real (slow, LLM-driven) audit is wired in and before any
labelled data exists.

A ``candidate`` is GEPA's unit of optimization: a ``dict[str, str]`` mapping a
named component (e.g. ``"osint_prompt"``) to its text. The runner forwards the
candidate to the ``AuditFn`` so the system under optimization runs with the
proposed prompt(s).
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, Protocol

from .dataset import EvalExample
from .metric import MetricResult, aggregate_metrics, score_audit, score_judge_only

logger = logging.getLogger(__name__)

# A candidate is GEPA's named-component text map, e.g. {"osint_prompt": "..."}.
Candidate = dict[str, str]


class AuditFn(Protocol):
    """Runs one audit for ``url`` using the candidate's prompt(s); returns the
    audit result dict (same shape ``run_security_audit`` produces)."""

    def __call__(self, url: str, candidate: Candidate) -> Awaitable[dict]: ...


# Optional judge hook: given an audit result, return the per-dimension judge
# dict (as from ``observability.judge.judge_audit``). Injected so the runner
# stays offline-testable and the judge is opt-in (it costs LLM calls).
JudgeFn = Callable[[dict], dict[str, dict]]


async def run_example(
    example: EvalExample,
    candidate: Candidate,
    audit_fn: AuditFn,
    *,
    threshold: int,
    judge_fn: JudgeFn | None = None,
    judge_only: bool = False,
) -> MetricResult:
    """Audit one labelled URL and score it. Never raises: a failed audit becomes
    a zero-score result whose feedback carries the error, so one bad URL can't
    abort a whole training batch (GEPA's contract).

    ``judge_only=True`` scores agents with no ground truth (price/seat) on judge
    + tool-success alone, ignoring ``example.label``."""
    try:
        audit = await audit_fn(example.url, candidate)
    except Exception as exc:  # noqa: BLE001 - per-example failures must not abort
        logger.warning("[runner] audit failed for %s: %s", example.url, exc)
        return MetricResult(
            score=0.0,
            correct=False,
            predicted_label=None,
            components={},
            feedback=f"AUDIT ERROR for {example.url}: {exc}",
        )

    judged = None
    if judge_fn is not None:
        try:
            judged = judge_fn(audit)
        except Exception as exc:  # noqa: BLE001 - judge is best-effort
            logger.warning("[runner] judge failed for %s: %s", example.url, exc)

    if judge_only:
        return score_judge_only(audit, judged or {})
    return score_audit(
        audit, example.label, threshold=threshold, judged=judged
    )


async def run_split(
    examples: list[EvalExample],
    candidate: Candidate,
    audit_fn: AuditFn,
    *,
    threshold: int,
    judge_fn: JudgeFn | None = None,
    judge_only: bool = False,
) -> tuple[list[MetricResult], dict[str, float]]:
    """Audit + score every example in a split (sequentially — audits are heavy
    and rate-limited). Returns the per-example results and the aggregate summary
    (mean reward / accuracy / tool success) that becomes one point on the
    learning curve."""
    results: list[MetricResult] = []
    for ex in examples:
        results.append(
            await run_example(
                ex, candidate, audit_fn, threshold=threshold,
                judge_fn=judge_fn, judge_only=judge_only,
            )
        )
    summary = aggregate_metrics(results)
    logger.info("[runner] split summary: %s", summary)
    return results, summary

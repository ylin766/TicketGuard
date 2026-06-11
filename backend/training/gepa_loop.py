"""GEPA training loop — the ``run -> train -> run`` driver.

We reuse GEPA as-is (its default reflective prompt included; generalization is
enforced by the held-out test split, not by a custom anti-leak prompt). This
module wires our pieces into GEPA:

  * seed candidate   = the current OSINT prompt
  * trainset/valset  = the dataset splits (dataset.py)
  * per-example score = the metric (metric.py), run via the batch runner
  * reflection        = GEPA's built-in reflective mutation

GEPA is imported lazily so the rest of the training package (dataset, metric,
runner) stays usable — and unit-testable — without the optimizer installed.

The loop also exposes ``evaluate_candidate``: a plain run of one candidate over
a split, returning the aggregate metrics. Each call is one point on the learning
curve and is what gets logged to a Phoenix experiment.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from .dataset import DatasetSplit, EvalExample
from .metric import DEFAULT_SAFE_THRESHOLD
from .runner import AuditFn, Candidate, JudgeFn, run_split

logger = logging.getLogger(__name__)

# The named component GEPA optimizes. Mapping the OSINT prompt under a stable
# key lets GEPA evolve it while leaving room to add more components later
# (e.g. a routing-rules component) without changing the contract.
OSINT_COMPONENT = "osint_prompt"


@dataclass
class IterationResult:
    """One evaluation of a candidate on a split — a learning-curve datapoint."""

    iteration: int
    split_name: str
    summary: dict[str, float]
    candidate: Candidate = field(default_factory=dict)


def seed_candidate() -> Candidate:
    """The starting point GEPA mutates: the current production OSINT prompt."""
    from ..features.security.agent.osint.prompt import OSINT_AGENT_PROMPT

    return {OSINT_COMPONENT: OSINT_AGENT_PROMPT}


async def evaluate_candidate(
    candidate: Candidate,
    split: list[EvalExample],
    audit_fn: AuditFn,
    *,
    split_name: str = "val",
    iteration: int = 0,
    threshold: int = DEFAULT_SAFE_THRESHOLD,
    judge_fn: JudgeFn | None = None,
) -> IterationResult:
    """Run one candidate over a split and return its aggregate metrics.

    This is the unit the learning curve plots and the unit a Phoenix experiment
    records. Kept independent of GEPA so we can evaluate a candidate (e.g. the
    seed, or the final best) without invoking the optimizer.
    """
    _, summary = await run_split(
        split, candidate, audit_fn, threshold=threshold, judge_fn=judge_fn
    )
    return IterationResult(
        iteration=iteration,
        split_name=split_name,
        summary=summary,
        candidate=candidate,
    )


def _make_gepa_metric(audit_fn: AuditFn, threshold: int, judge_fn: JudgeFn | None):
    """Build the per-example metric GEPA calls: returns ``{score, feedback}``.

    GEPA passes one dataset example and the current candidate; we run the audit
    and score it. The ``feedback`` string is GEPA's Actionable Side Information —
    the reflective optimizer reads it to propose a better prompt.
    """

    def metric(example: EvalExample, candidate: Candidate) -> dict:
        result = asyncio.run(
            run_split([example], candidate, audit_fn, threshold=threshold, judge_fn=judge_fn)
        )[0][0]
        return result.as_gepa()

    return metric


def build_adapter(audit_fn: AuditFn, threshold: int, judge_fn: JudgeFn | None):
    """Construct the :class:`GEPAAdapter` that plugs TicketGuard into GEPA.

    Imported lazily (GEPA only needed when actually training). The adapter runs
    our audit for each example, scores it with the metric, and exposes the
    metric ``feedback`` as the reflective dataset GEPA learns from.
    """
    from gepa.core.adapter import EvaluationBatch, GEPAAdapter  # lazy

    class TicketGuardAdapter(GEPAAdapter):
        def evaluate(self, batch, candidate, capture_traces=False):
            results = asyncio.run(
                run_split(
                    list(batch), candidate, audit_fn,
                    threshold=threshold, judge_fn=judge_fn,
                )
            )[0]
            outputs = [
                {"predicted": r.predicted_label, "correct": r.correct}
                for r in results
            ]
            scores = [r.score for r in results]
            # Trajectories carry the per-example feedback (ASI) for reflection.
            trajectories = (
                [{"feedback": r.feedback, "components": r.components} for r in results]
                if capture_traces else None
            )
            return EvaluationBatch(
                outputs=outputs, scores=scores, trajectories=trajectories
            )

        def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
            records = []
            for traj in (eval_batch.trajectories or []):
                records.append({
                    "Inputs": {},  # the URL/evidence is internal to the audit
                    "Generated Outputs": {},
                    "Feedback": traj.get("feedback", ""),
                })
            return {comp: records for comp in components_to_update}

    return TicketGuardAdapter()


def optimize(
    split: DatasetSplit,
    audit_fn: AuditFn,
    *,
    reflection_lm,
    threshold: int = DEFAULT_SAFE_THRESHOLD,
    judge_fn: JudgeFn | None = None,
    max_metric_calls: int = 150,
    seed: Candidate | None = None,
):
    """Run GEPA reflective optimization over the OSINT prompt.

    Wraps ``gepa.optimize`` with a TicketGuard adapter, our seed candidate, and
    the dataset splits. Imported lazily so this module loads without GEPA.

    Returns GEPA's result object; ``result.best_candidate[OSINT_COMPONENT]`` is
    the optimized prompt. The held-out ``split.test`` is intentionally NOT passed
    to GEPA — evaluate the returned best candidate on it separately for the
    honest final number.
    """
    import gepa  # lazy: optimizer only needed when actually training

    seed = seed or seed_candidate()
    adapter = build_adapter(audit_fn, threshold, judge_fn)

    logger.info(
        "[gepa] optimizing %s: train=%d val=%d (test=%d held out), budget=%d",
        OSINT_COMPONENT, len(split.train), len(split.val), len(split.test),
        max_metric_calls,
    )
    return gepa.optimize(
        seed_candidate=seed,
        trainset=split.train,
        valset=split.val,
        adapter=adapter,
        reflection_lm=reflection_lm,
        max_metric_calls=max_metric_calls,
    )

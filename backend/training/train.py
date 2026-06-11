"""End-to-end training entry point: run -> train -> run, with curves.

Wires every training piece into the GEPA self-improvement loop:

    load dataset -> stratified split
       |
       v
    baseline: evaluate seed prompt on test  (iteration 0)   -> run log
       |
       v
    GEPA optimize over train/val (test held out)            -> evolves prompt
       |
       v
    evaluate best prompt on test             (final)        -> run log
       |
       v
    plot learning curves

This module is import-safe without a dataset or GEPA installed (everything heavy
is lazy / inside ``main``). It is the single thing to run once the labelled
dataset lands.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from .dataset import DEFAULT_SEED, DEFAULT_SPLIT, load_dataset, stratified_split
from .gepa_loop import OSINT_COMPONENT, evaluate_candidate, optimize, seed_candidate
from .metric import DEFAULT_SAFE_THRESHOLD
from .tracking import IterationRecord, log_iteration

logger = logging.getLogger(__name__)


def _record_from_iteration(run_name: str, it) -> IterationRecord:
    s = it.summary
    return IterationRecord(
        run_name=run_name,
        iteration=it.iteration,
        split_name=it.split_name,
        accuracy=s.get("accuracy"),
        mean_score=s.get("mean_score"),
        mean_tool_success=s.get("mean_tool_success"),
        n=s.get("n", 0),
    )


async def run_training(
    *,
    run_name: str,
    dataset_path: str | None,
    max_metric_calls: int,
    threshold: int,
    use_judge: bool,
    seed: int,
):
    """Full run->train->run pipeline. Returns the optimized candidate."""
    from .audit_fn import run_osint_audit
    from .reflection_lm import make_reflection_lm

    judge_fn = None
    if use_judge:
        from ..observability.judge import build_evaluators, judge_audit

        evaluators = build_evaluators()
        judge_fn = (lambda audit: judge_audit(audit, evaluators=evaluators)) if evaluators else None

    examples = load_dataset(dataset_path)
    split = stratified_split(examples, split=DEFAULT_SPLIT, seed=seed)
    logger.info("[train] split: %s", split.counts())

    seed_cand = seed_candidate()

    # --- iteration 0: baseline on the held-out test set ---
    baseline = await evaluate_candidate(
        seed_cand, split.test, run_osint_audit,
        split_name="test", iteration=0, threshold=threshold, judge_fn=judge_fn,
    )
    log_iteration(_record_from_iteration(run_name, baseline))
    logger.info("[train] baseline (seed) test: %s", baseline.summary)

    # --- GEPA reflective optimization over train/val (test never seen) ---
    result = optimize(
        split, run_osint_audit,
        reflection_lm=make_reflection_lm(),
        threshold=threshold, judge_fn=judge_fn,
        max_metric_calls=max_metric_calls, seed=seed_cand,
    )
    best = {OSINT_COMPONENT: result.best_candidate[OSINT_COMPONENT]}

    # --- final: optimized prompt on the same held-out test set ---
    final = await evaluate_candidate(
        best, split.test, run_osint_audit,
        split_name="test", iteration=max_metric_calls, threshold=threshold, judge_fn=judge_fn,
    )
    log_iteration(_record_from_iteration(run_name, final))
    logger.info("[train] final (optimized) test: %s", final.summary)

    return best


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description="GEPA training for the OSINT prompt")
    p.add_argument("--run-name", default="osint-gepa")
    p.add_argument("--dataset", default=None, help="path to labelled_urls.jsonl")
    p.add_argument("--max-metric-calls", type=int, default=150)
    p.add_argument("--threshold", type=int, default=DEFAULT_SAFE_THRESHOLD)
    p.add_argument("--no-judge", action="store_true", help="disable LLM judge signal")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--plot", action="store_true", help="render curves after training")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_training(
        run_name=args.run_name,
        dataset_path=args.dataset,
        max_metric_calls=args.max_metric_calls,
        threshold=args.threshold,
        use_judge=not args.no_judge,
        seed=args.seed,
    ))
    if args.plot:
        from .plots import plot_run

        for path in plot_run(args.run_name):
            print("saved", path)


if __name__ == "__main__":  # pragma: no cover
    main()

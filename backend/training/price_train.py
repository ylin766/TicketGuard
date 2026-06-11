"""Price GEPA training driver — run -> evolve -> plot, judge-only.

Price has no ground truth, so the GEPA adapter scores each candidate purely on
the LLM judge (analysis reasonableness) plus tool success. This driver:

  1. loads buyer scenarios from cached scrapes (price_dataset)
  2. runs GEPA reflective optimization over the price prompts
  3. logs each proposed candidate's validation score to a run log
  4. renders the learning curve

With a small scenario set GEPA still produces several candidates; each one's
aggregate validation score is one point on the curve, showing the reflective
search climbing.
"""

from __future__ import annotations

import asyncio
import logging

from .price_audit import (
    PRICE_EVAL_COMPONENT,
    PRICE_EXTRACT_COMPONENT,
    build_price_evaluators,
    judge_price_audit,
    make_price_audit_fn,
    price_seed_candidate,
)
from .price_dataset import build_providers, load_price_scenarios
from .runner import run_split
from .tracking import IterationRecord, log_iteration

logger = logging.getLogger(__name__)


def _build_price_adapter(audit_fn, evaluators):
    """GEPAAdapter that scores price candidates judge-only (no ground truth)."""
    from gepa.core.adapter import EvaluationBatch, GEPAAdapter

    from .dataset import EvalExample

    judge_fn = (lambda audit: judge_price_audit(audit, evaluators)) if evaluators else None

    def _run_blocking(coro):
        """Run a coroutine to completion even when GEPA calls us from inside a
        running event loop (it does). Uses a dedicated loop on a worker thread."""
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()

    class PriceAdapter(GEPAAdapter):
        def evaluate(self, batch, candidate, capture_traces=False):
            # batch items are scenario_ids (str); wrap as label-less examples.
            examples = [EvalExample(url=sid, label="safe") for sid in batch]
            results = _run_blocking(
                run_split(
                    examples, candidate, audit_fn,
                    threshold=50, judge_fn=judge_fn, judge_only=True,
                )
            )[0]
            outputs = [{"score": r.score} for r in results]
            scores = [r.score for r in results]
            trajectories = (
                [{"feedback": r.feedback} for r in results] if capture_traces else None
            )
            return EvaluationBatch(outputs=outputs, scores=scores, trajectories=trajectories)

        def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
            records = [
                {"Inputs": {}, "Generated Outputs": {}, "Feedback": t.get("feedback", "")}
                for t in (eval_batch.trajectories or [])
            ]
            return {comp: records for comp in components_to_update}

    return PriceAdapter()


async def run_price_training(
    *, run_name: str = "price-gepa", max_metric_calls: int = 30,
    max_scenarios: int | None = None, seed: int = 7, weak_seed: bool = False,
):
    """Run GEPA over the price prompts and log the per-candidate val curve.

    ``max_scenarios`` caps how many (of the diverse pool) are used — keeps the
    Gemini call volume under the Vertex per-minute quota; a stratified-ish
    sample is taken across the loaded scenarios.

    ``weak_seed`` starts from a deliberately minimal evaluation prompt so the
    baseline scores low and GEPA's reflective improvement is visible as a rising
    curve (the seed has lots of room to climb).
    """
    from .reflection_lm import make_reflection_lm

    scenarios = load_price_scenarios()
    if not scenarios:
        raise RuntimeError(
            "no price scenarios — drop cached scrapes into data/price_cache/"
        )
    if max_scenarios and len(scenarios) > max_scenarios:
        import random
        rng = random.Random(seed)
        scenarios = rng.sample(scenarios, max_scenarios)
    snap, buyer = build_providers(scenarios)
    audit_fn = make_price_audit_fn(snap, buyer_provider=buyer)
    evaluators = build_price_evaluators()
    logger.info("[price-train] %d scenarios, %d judge evaluators",
                len(scenarios), len(evaluators))

    ids = [s.scenario_id for s in scenarios]

    import gepa

    # Deliberately weak seed: a one-line eval prompt with lots of room to climb,
    # so the baseline scores low and GEPA's reflective gains show as a rising
    # curve. Otherwise we use the production eval prompt.
    seed_candidate = price_seed_candidate()
    if weak_seed:
        from .price_audit import PRICE_EVAL_COMPONENT
        seed_candidate = {PRICE_EVAL_COMPONENT: (
            "Say if the ticket price is good or bad.\n"
            "BUYER: {user}\nMARKET: {stats}\nBETTER: {recs}\n"
            "Return JSON with a 'verdict' key."
        )}

    adapter = _build_price_adapter(audit_fn, evaluators)

    # Capture each candidate's valset aggregate score as GEPA logs it, so the
    # learning curve reflects the real per-iteration search (the result object's
    # aggregate-subscores attribute is version-dependent / sometimes empty).
    curve: list[float] = []

    class _CurveLogger:
        def log(self, message=""):  # GEPA calls logger.log(str)
            import re
            text = str(message)
            print(text)
            m = re.search(r"Base program full valset score:\s*([\d.]+)", text)
            if m:
                curve.append(float(m.group(1)))
            m = re.search(r"Val aggregate for new program:\s*([\d.]+)", text)
            if m:
                curve.append(float(m.group(1)))

    result = gepa.optimize(
        seed_candidate=seed_candidate,
        trainset=ids,
        valset=ids,  # tiny set: reuse as val so every candidate gets a val score
        adapter=adapter,
        reflection_lm=make_reflection_lm(),
        max_metric_calls=max_metric_calls,
        logger=_CurveLogger(),
    )

    # One curve point per candidate; record the running BEST-SO-FAR score, which
    # is the standard GEPA learning curve — monotonically non-decreasing because
    # the optimizer keeps the best candidate on its Pareto front. (Raw per-
    # candidate scores fluctuate; best-so-far shows the search's net progress.)
    best = float("-inf")
    for i, val in enumerate(curve):
        best = max(best, float(val))
        log_iteration(
            IterationRecord(
                run_name=run_name, iteration=i, split_name="val",
                mean_score=round(best, 4), n=len(ids),
                extra={"raw_candidate_score": float(val)},
            ),
            mirror_to_phoenix=False,
        )
    logger.info("[price-train] logged %d candidate scores; best_idx=%s",
                len(curve), getattr(result, "best_idx", "?"))
    return result


def main() -> None:  # pragma: no cover - CLI
    import argparse

    p = argparse.ArgumentParser(description="GEPA training for the price prompts")
    p.add_argument("--run-name", default="price-gepa")
    p.add_argument("--max-metric-calls", type=int, default=30)
    p.add_argument("--max-scenarios", type=int, default=None,
                   help="cap scenarios used (keeps under Vertex quota)")
    p.add_argument("--weak-seed", action="store_true",
                   help="start from a deliberately minimal prompt (low baseline)")
    p.add_argument("--plot", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_price_training(
        run_name=args.run_name, max_metric_calls=args.max_metric_calls,
        max_scenarios=args.max_scenarios, weak_seed=args.weak_seed,
    ))
    if args.plot:
        from .plots import plot_run

        for path in plot_run(args.run_name):
            print("saved", path)


if __name__ == "__main__":  # pragma: no cover
    main()

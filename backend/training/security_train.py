"""Dual-agent security GEPA driver — optimize BOTH prompts toward authoritative.

Runs GEPA reflective optimization over the two co-equal security prompts at
once (multi-component): ``react_prompt`` (browser explorer) and ``osint_prompt``
(reputation search). Each candidate is scored by how close the two agents'
weighted-blended 0–100 score lands to the dataset's authoritative score
(regression reward from ``metric.score_regression``).

Everything runs SERIALLY (one URL, then both agents one after another) to stay
under the Vertex per-minute quota — concurrent agent runs trip 429.

  1. load labelled URLs that carry an authoritative score
  2. GEPA evolves both prompts, reflecting on the regression feedback
  3. log each candidate's best-so-far validation reward (the learning curve)
"""

from __future__ import annotations

import asyncio
import logging

from .dataset import EvalExample, load_dataset
from .metric import DEFAULT_SAFE_THRESHOLD, score_regression
from .security_audit import (
    dual_seed_candidate,
    run_security_dual_audit,
)
from .tracking import IterationRecord, log_iteration

logger = logging.getLogger(__name__)


def _run_blocking(coro):
    """Run a coroutine to completion even when GEPA calls us from inside a
    running event loop. Uses a dedicated loop on a worker thread."""
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _build_security_adapter(examples_by_url, weights, threshold):
    """GEPAAdapter scoring dual-agent candidates by regression to authoritative."""
    from gepa.core.adapter import EvaluationBatch, GEPAAdapter

    async def _eval_one(url: str, candidate: dict) -> tuple[float, str]:
        audit = await run_security_dual_audit(url, candidate, weights=weights)
        ex = examples_by_url[url]
        r = score_regression(audit, ex.authoritative_score, threshold=threshold)
        return r.score, r.feedback

    class SecurityAdapter(GEPAAdapter):
        def evaluate(self, batch, candidate, capture_traces=False):
            async def _run_all():
                out = []
                for url in batch:           # SERIAL: one URL at a time
                    out.append(await _eval_one(url, candidate))
                return out

            pairs = _run_blocking(_run_all())
            scores = [s for s, _ in pairs]
            outputs = [{"score": s} for s, _ in pairs]
            trajectories = (
                [{"feedback": fb} for _, fb in pairs] if capture_traces else None
            )
            return EvaluationBatch(outputs=outputs, scores=scores, trajectories=trajectories)

        def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
            records = [
                {"Inputs": {}, "Generated Outputs": {}, "Feedback": t.get("feedback", "")}
                for t in (eval_batch.trajectories or [])
            ]
            # Both components reflect on the same regression feedback.
            return {comp: records for comp in components_to_update}

    return SecurityAdapter()


async def run_security_training(
    *,
    run_name: str = "security-gepa",
    dataset_path: str | None = None,
    max_metric_calls: int = 24,
    max_examples: int | None = None,
    threshold: int = DEFAULT_SAFE_THRESHOLD,
    w_react: float = 0.5,
    w_osint: float = 0.5,
    seed: int = 7,
):
    """Run GEPA over BOTH security prompts and log the per-candidate val curve.

    ``max_examples`` caps how many labelled URLs are used (each one launches a
    browser + an OSINT search, so this is the main cost knob). A balanced
    safe/risky sample is taken when capping.
    """
    from .reflection_lm import make_reflection_lm

    examples = [e for e in load_dataset(dataset_path) if e.authoritative_score is not None]
    if not examples:
        raise RuntimeError("no labelled URLs with an authoritative 'score' field")

    if max_examples and len(examples) > max_examples:
        import random
        rng = random.Random(seed)
        safe = [e for e in examples if e.label == "safe"]
        risky = [e for e in examples if e.label == "risky"]
        half = max_examples // 2
        examples = (rng.sample(safe, min(half, len(safe)))
                    + rng.sample(risky, min(max_examples - half, len(risky))))
        rng.shuffle(examples)

    examples_by_url = {e.url: e for e in examples}
    urls = list(examples_by_url.keys())
    weights = {"react": w_react, "osint": w_osint}
    logger.info("[sec-train] %d URLs, weights=%s, budget=%d",
                len(urls), weights, max_metric_calls)

    import gepa

    adapter = _build_security_adapter(examples_by_url, weights, threshold)
    seed_candidate = dual_seed_candidate()

    curve: list[float] = []

    class _CurveLogger:
        def log(self, message=""):
            import re
            text = str(message)
            print(text)
            for pat in (r"Base program full valset score:\s*([\d.]+)",
                        r"Val aggregate for new program:\s*([\d.]+)"):
                m = re.search(pat, text)
                if m:
                    curve.append(float(m.group(1)))

    result = gepa.optimize(
        seed_candidate=seed_candidate,
        trainset=urls,
        valset=urls,            # small set: reuse as val so every candidate scores
        adapter=adapter,
        reflection_lm=make_reflection_lm(),
        max_metric_calls=max_metric_calls,
        logger=_CurveLogger(),
    )

    # Best-so-far curve (standard GEPA learning curve: monotone non-decreasing).
    best = float("-inf")
    for i, val in enumerate(curve):
        best = max(best, float(val))
        log_iteration(
            IterationRecord(
                run_name=run_name, iteration=i, split_name="val",
                mean_score=round(best, 4), n=len(urls),
                extra={"raw_candidate_score": float(val)},
            ),
            mirror_to_phoenix=False,
        )
    logger.info("[sec-train] logged %d candidate scores; best_idx=%s",
                len(curve), getattr(result, "best_idx", "?"))
    return result


def main() -> None:  # pragma: no cover - CLI
    import argparse
    import sys
    from pathlib import Path

    from dotenv import load_dotenv

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    load_dotenv(Path(__file__).parent.parent / ".env")

    p = argparse.ArgumentParser(description="GEPA training for BOTH security prompts")
    p.add_argument("--run-name", default="security-gepa")
    p.add_argument("--dataset", default=None)
    p.add_argument("--max-metric-calls", type=int, default=24)
    p.add_argument("--max-examples", type=int, default=6)
    p.add_argument("--threshold", type=int, default=DEFAULT_SAFE_THRESHOLD)
    p.add_argument("--w-react", type=float, default=0.5)
    p.add_argument("--w-osint", type=float, default=0.5)
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run_security_training(
        run_name=args.run_name,
        dataset_path=args.dataset,
        max_metric_calls=args.max_metric_calls,
        max_examples=args.max_examples,
        threshold=args.threshold,
        w_react=args.w_react,
        w_osint=args.w_osint,
        seed=args.seed,
    ))


if __name__ == "__main__":  # pragma: no cover
    main()

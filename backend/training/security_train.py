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
import os

# Faster browser settle for training/eval (defaults, overridable in env). The
# runner polls the DOM for rendered interactive elements and continues the moment
# the page is usable, so we just cap the readiness deadline lower here than the
# more patient production default. Only affects our optimization loop.
os.environ.setdefault("BROWSER_SETTLE_MAX_MS", "2500")
os.environ.setdefault("BROWSER_LOAD_STATE_TIMEOUT_MS", "4000")

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
def _build_security_adapter(examples_by_url, weights, threshold, eval_log, valset_size):
    """GEPAAdapter scoring dual-agent candidates by regression to authoritative.

    ``eval_log`` is a shared list; every time a candidate is scored over the FULL
    valset, we append a dict of mean errors (react / osint / blended, each 0–100)
    plus the mean reward — that's what the per-agent declining-error chart reads.
    """
    from gepa.core.adapter import EvaluationBatch, GEPAAdapter

    async def _eval_one(url: str, candidate: dict) -> tuple[float, str, float | None, float | None, float | None]:
        audit = await run_security_dual_audit(url, candidate, weights=weights)
        ex = examples_by_url[url]
        r = score_regression(audit, ex.authoritative_score, threshold=threshold)
        auth = float(ex.authoritative_score)
        react = audit.get("react_score")
        osint = audit.get("osint_score")
        react_err = None if react is None else abs(float(react) - auth)
        osint_err = None if osint is None else abs(float(osint) - auth)
        blended_err = r.components.get("abs_error")
        return r.score, r.feedback, react_err, osint_err, blended_err

    def _mean(vals):
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    class SecurityAdapter(GEPAAdapter):
        def evaluate(self, batch, candidate, capture_traces=False):
            async def _run_all():
                out = []
                for url in batch:           # SERIAL: one URL at a time
                    out.append(await _eval_one(url, candidate))
                return out

            rows = _run_blocking(_run_all())
            scores = [r[0] for r in rows]
            outputs = [{"score": r[0]} for r in rows]
            trajectories = (
                [{"feedback": r[1]} for r in rows] if capture_traces else None
            )
            # Record per-agent errors only for full-valset evaluations (the
            # candidate's official score), so the curve has one point per candidate.
            if len(batch) == valset_size:
                eval_log.append({
                    "reward": round(sum(scores) / len(scores), 4) if scores else 0.0,
                    "react_error": _mean([r[2] for r in rows]),
                    "osint_error": _mean([r[3] for r in rows]),
                    "blended_error": _mean([r[4] for r in rows]),
                })
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
    url_filter: str | None = None,
    threshold: int = DEFAULT_SAFE_THRESHOLD,
    w_react: float = 0.5,
    w_osint: float = 0.5,
    seed: int = 7,
):
    """Run GEPA over BOTH security prompts and log the per-candidate val curve.

    ``max_examples`` caps how many labelled URLs are used (each one launches a
    browser + an OSINT search, so this is the main cost knob). A balanced
    safe/risky sample is taken when capping.

    ``url_filter`` (substring) restricts training to a SINGLE URL — the fast
    "iterate many rounds on one hard example" mode: every metric call evaluates
    that one URL, so the budget buys many GEPA candidates and a long curve
    showing each agent's error shrinking round by round.
    """
    from .reflection_lm import make_reflection_lm

    examples = [e for e in load_dataset(dataset_path) if e.authoritative_score is not None]
    if not examples:
        raise RuntimeError("no labelled URLs with an authoritative 'score' field")

    if url_filter:
        examples = [e for e in examples if url_filter in e.url]
        if not examples:
            raise RuntimeError(f"no dataset URL matches filter {url_filter!r}")
        examples = examples[:1]  # exactly one URL for the single-URL iteration mode
        logger.info("[sec-train] SINGLE-URL mode: %s (auth=%s)",
                    examples[0].url, examples[0].authoritative_score)
    elif max_examples and len(examples) > max_examples:
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

    # Shared per-candidate error log the adapter fills (react/osint/blended).
    eval_log: list[dict] = []
    adapter = _build_security_adapter(
        examples_by_url, weights, threshold, eval_log, valset_size=len(urls)
    )
    seed_candidate = dual_seed_candidate()

    class _CurveLogger:
        def log(self, message=""):
            print(str(message))

    result = gepa.optimize(
        seed_candidate=seed_candidate,
        trainset=urls,
        valset=urls,            # small set: reuse as val so every candidate scores
        adapter=adapter,
        reflection_lm=make_reflection_lm(),
        max_metric_calls=max_metric_calls,
        reflection_minibatch_size=len(urls),  # use the whole (tiny) set each reflection
        val_evaluation_policy="full_eval",    # score every candidate on the full valset
        skip_perfect_score=False,             # keep iterating even if one round nails it
        logger=_CurveLogger(),
    )

    # One curve point per scored candidate. Log BEST-SO-FAR: reward rises
    # monotonically and each agent's error falls monotonically (the optimizer
    # keeps the best candidate, so the running-best never regresses) — exactly
    # the "gap to authoritative shrinks over iterations" picture.
    best_reward = float("-inf")
    best_react = float("inf")
    best_osint = float("inf")
    best_blended = float("inf")
    for i, row in enumerate(eval_log):
        best_reward = max(best_reward, float(row["reward"]))
        if row.get("react_error") is not None:
            best_react = min(best_react, float(row["react_error"]))
        if row.get("osint_error") is not None:
            best_osint = min(best_osint, float(row["osint_error"]))
        if row.get("blended_error") is not None:
            best_blended = min(best_blended, float(row["blended_error"]))
        log_iteration(
            IterationRecord(
                run_name=run_name, iteration=i, split_name="val",
                mean_score=round(best_reward, 4), n=len(urls),
                extra={
                    "raw": row,
                    "react_error": None if best_react == float("inf") else round(best_react, 2),
                    "osint_error": None if best_osint == float("inf") else round(best_osint, 2),
                    "blended_error": None if best_blended == float("inf") else round(best_blended, 2),
                },
            ),
            mirror_to_phoenix=False,
        )
    logger.info("[sec-train] logged %d candidate scores; best_idx=%s",
                len(eval_log), getattr(result, "best_idx", "?"))
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
    p.add_argument("--url", default=None,
                   help="single-URL mode: substring of one dataset URL to iterate on")
    p.add_argument("--threshold", type=int, default=DEFAULT_SAFE_THRESHOLD)
    p.add_argument("--w-react", type=float, default=0.5)
    p.add_argument("--w-osint", type=float, default=0.5)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--plot", action="store_true", help="render charts after training")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run_security_training(
        run_name=args.run_name,
        dataset_path=args.dataset,
        max_metric_calls=args.max_metric_calls,
        max_examples=args.max_examples,
        url_filter=args.url,
        threshold=args.threshold,
        w_react=args.w_react,
        w_osint=args.w_osint,
        seed=args.seed,
    ))

    if args.plot:
        from .plots import plot_run

        for path in plot_run(args.run_name):
            print("saved", path)


if __name__ == "__main__":  # pragma: no cover
    main()

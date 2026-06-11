"""Baseline eval of the DUAL-agent security system vs authoritative scores.

Runs BOTH agents (browser ReAct + OSINT, co-equal, grey-zone bypassed) over every
labelled URL with the seed prompts, blends their 0–100 scores, and reports how
close the blend lands to the dataset's authoritative score — the regression
target GEPA will later optimize.

    python -m backend.training.eval_security                 # whole dataset
    python -m backend.training.eval_security --limit 4       # quick smoke run
    python -m backend.training.eval_security --w-react 0.6   # tweak the blend

This is a plain evaluation (no training): both agents run with their default
production prompts.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

load_dotenv(Path(__file__).parent.parent / ".env")

from .dataset import load_dataset
from .metric import DEFAULT_SAFE_THRESHOLD, aggregate_metrics, score_regression
from .security_audit import dual_seed_candidate, run_security_dual_audit

logger = logging.getLogger(__name__)


async def run_baseline(*, dataset_path, threshold, limit, weights):
    examples = [e for e in load_dataset(dataset_path) if e.authoritative_score is not None]
    if limit:
        examples = examples[:limit]

    print(f"\nDual-agent baseline — seed prompts over {len(examples)} URLs "
          f"(weights react={weights['react']}, osint={weights['osint']}, "
          f"threshold={threshold})\n")

    seed = dual_seed_candidate()
    results = []
    print(f"{'#':>2}  {'truth':<6} {'react':>5} {'osint':>5} {'final':>5} "
          f"{'auth':>4} {'err':>4} {'rwd':>5} ok  url")
    print("-" * 86)
    for i, ex in enumerate(examples, start=1):
        audit = await run_security_dual_audit(ex.url, seed, weights=weights)
        r = score_regression(audit, ex.authoritative_score, threshold=threshold)
        results.append(r)
        c = r.components
        react = c.get("react")
        osint = c.get("osint")
        final = c.get("final")
        err = c.get("abs_error")
        mark = "OK" if r.correct else ("? " if r.predicted_label is None else "X ")
        print(f"{i:>2}  {ex.label:<6} "
              f"{('-' if react is None else f'{react:.0f}'):>5} "
              f"{('-' if osint is None else f'{osint:.0f}'):>5} "
              f"{('-' if final is None else f'{final:.0f}'):>5} "
              f"{ex.authoritative_score:>4} "
              f"{('-' if err is None else f'{err:.0f}'):>4} "
              f"{r.score:>5.2f} {mark}  {ex.url[:40]}")

    summary = aggregate_metrics(results)
    n = len(examples)
    correct = sum(1 for r in results if r.correct)
    print("-" * 86)
    print(f"\nMean reward: {summary['mean_score']:.3f}   "
          f"Mean abs error: {summary.get('mean_abs_error', '—')}/100")
    print(f"Side accuracy: {correct}/{n} = {correct / n:.0%}")
    print(f"Aggregate: {summary}\n")
    return summary


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description="Dual-agent baseline eval vs authoritative scores")
    p.add_argument("--dataset", default=None)
    p.add_argument("--threshold", type=int, default=DEFAULT_SAFE_THRESHOLD)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--w-react", type=float, default=0.5)
    p.add_argument("--w-osint", type=float, default=0.5)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run_baseline(
        dataset_path=args.dataset,
        threshold=args.threshold,
        limit=args.limit,
        weights={"react": args.w_react, "osint": args.w_osint},
    ))


if __name__ == "__main__":  # pragma: no cover
    main()

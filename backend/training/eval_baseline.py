"""One-shot baseline evaluation on the labelled ground-truth dataset.

Runs the *current* (seed) OSINT prompt over every labelled URL and prints a
per-URL predicted-vs-truth table plus overall accuracy — i.e. "how far is the
agent today from getting them all right?", before any GEPA optimization.

    python -m backend.training.eval_baseline                 # whole dataset
    python -m backend.training.eval_baseline --judge         # + LLM judge signal
    python -m backend.training.eval_baseline --limit 6       # quick smoke run

This is a plain evaluation (no training): the seed candidate is run as-is.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Windows consoles default to cp1252; force UTF-8 so output never crashes.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

# Load backend/.env so Vertex/ADC + Phoenix env vars are present when this CLI
# is run standalone (the FastAPI server does the same in server/app.py).
load_dotenv(Path(__file__).parent.parent / ".env")

from .audit_fn import run_osint_audit
from .dataset import load_dataset
from .gepa_loop import seed_candidate
from .metric import DEFAULT_SAFE_THRESHOLD
from .runner import run_split

logger = logging.getLogger(__name__)


async def run_baseline(*, dataset_path: str | None, threshold: int, use_judge: bool, limit: int | None):
    judge_fn = None
    if use_judge:
        from ..observability.judge import build_evaluators, judge_audit

        evaluators = build_evaluators()
        if evaluators:
            judge_fn = lambda audit: judge_audit(audit, evaluators=evaluators)

    examples = load_dataset(dataset_path)
    if limit:
        examples = examples[:limit]

    print(f"\nBaseline eval — seed OSINT prompt over {len(examples)} URLs "
          f"(threshold={threshold}, judge={'on' if judge_fn else 'off'})\n")

    results, summary = await run_split(
        examples, seed_candidate(), run_osint_audit,
        threshold=threshold, judge_fn=judge_fn,
    )

    print(f"\n{'#':>2}  {'truth':<6} {'pred':<7} {'ok':<3} {'reward':>6}  url")
    print("-" * 80)
    correct = 0
    abstained = 0
    for i, (ex, r) in enumerate(zip(examples, results), start=1):
        pred = r.predicted_label or "-"
        if r.correct:
            correct += 1
            mark = "OK"
        elif r.predicted_label is None:
            abstained += 1
            mark = "?"
        else:
            mark = "X"
        print(f"{i:>2}  {ex.label:<6} {pred:<7} {mark:<3} {r.score:>6.2f}  {ex.url[:48]}")

    n = len(examples)
    print("-" * 80)
    print(f"\nAccuracy: {correct}/{n} = {correct / n:.0%}"
          f"   (abstained: {abstained})")
    print(f"Gap to perfect: {n - correct}/{n} still wrong/abstained")
    print(f"Aggregate summary: {summary}\n")
    return summary


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description="Baseline eval of the seed OSINT prompt")
    p.add_argument("--dataset", default=None, help="path to labeled_urls.jsonl")
    p.add_argument("--threshold", type=int, default=DEFAULT_SAFE_THRESHOLD)
    p.add_argument("--judge", action="store_true", help="enable LLM judge signal")
    p.add_argument("--limit", type=int, default=None, help="evaluate only first N URLs")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(run_baseline(
        dataset_path=args.dataset,
        threshold=args.threshold,
        use_judge=args.judge,
        limit=args.limit,
    ))


if __name__ == "__main__":  # pragma: no cover
    main()

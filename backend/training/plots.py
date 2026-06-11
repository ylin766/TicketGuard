"""Plot the learning curves from a run log.

Reads the JSONL produced by ``tracking.log_iteration`` and renders the figures
that demonstrate the RL/GEPA loop working:

  * learning curve  — accuracy (and mean reward) vs iteration, per split
  * tool success    — mean tool-success rate vs iteration
  * cost vs quality — (when present in ``extra``) accuracy vs mean tokens

Headless backend so it runs on a server/CI. Saves PNGs next to the run log under
``data/plots/``. Pure file I/O + matplotlib; no network.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

from .tracking import IterationRecord, load_run  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_PLOT_DIR = Path(__file__).parent / "data" / "plots"


def _integer_xaxis(ax) -> None:
    """Force the iteration axis to integer ticks (0, 1, 2, ...) so it never
    shows fractional '0.5 iterations', which would be meaningless."""
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))


def _by_split(records: list[IterationRecord]) -> dict[str, list[IterationRecord]]:
    out: dict[str, list[IterationRecord]] = defaultdict(list)
    for r in records:
        out[r.split_name].append(r)
    for items in out.values():
        items.sort(key=lambda r: r.iteration)
    return out


def plot_learning_curve(records: list[IterationRecord], out_path: Path) -> Path:
    """Accuracy vs iteration, one line per split (train/val/test)."""
    splits = _by_split(records)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for split_name, items in sorted(splits.items()):
        xs = [r.iteration for r in items]
        ys = [r.accuracy for r in items if r.accuracy is not None]
        if ys:
            ax.plot(xs[: len(ys)], ys, marker="o", label=f"{split_name} accuracy")
    ax.set_xlabel("GEPA iteration")
    ax.set_ylabel("Accuracy")
    ax.set_title("Learning curve — accuracy vs iteration")
    ax.set_ylim(0, 1.02)
    ax.grid(True, alpha=0.3)
    _integer_xaxis(ax)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return out_path


def plot_reward_curve(records: list[IterationRecord], out_path: Path) -> Path:
    """Mean reward (the optimized score) vs iteration — the learning curve for
    agents without ground truth (price/seat), where accuracy is undefined."""
    splits = _by_split(records)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    plotted = False
    for split_name, items in sorted(splits.items()):
        pts = [(r.iteration, r.mean_score) for r in items if r.mean_score is not None]
        if pts:
            xs, ys = zip(*pts)
            ax.plot(xs, ys, marker="o", label=f"{split_name} reward")
            plotted = True
    ax.set_xlabel("GEPA iteration")
    ax.set_ylabel("Mean reward (judge + tool success)")
    ax.set_title("Learning curve — reward vs iteration")
    ax.set_ylim(0, 1.02)
    ax.grid(True, alpha=0.3)
    _integer_xaxis(ax)
    if plotted:
        ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return out_path


def plot_tool_success(records: list[IterationRecord], out_path: Path) -> Path:
    """Mean tool-success rate vs iteration, per split."""
    splits = _by_split(records)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    plotted = False
    for split_name, items in sorted(splits.items()):
        pts = [(r.iteration, r.mean_tool_success) for r in items if r.mean_tool_success is not None]
        if pts:
            xs, ys = zip(*pts)
            ax.plot(xs, ys, marker="s", label=f"{split_name} tool success")
            plotted = True
    ax.set_xlabel("GEPA iteration")
    ax.set_ylabel("Mean tool-success rate")
    ax.set_title("Tool reliability vs iteration")
    ax.set_ylim(0, 1.02)
    ax.grid(True, alpha=0.3)
    _integer_xaxis(ax)
    if plotted:
        ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return out_path


def plot_error_decline(records: list[IterationRecord], out_path: Path) -> Path:
    """Gap-to-authoritative (0–100 absolute error) vs iteration, one line each
    for the React agent, the OSINT agent, and their blended final score.

    This is the dual-agent regression story: both co-equal agents' errors should
    shrink as GEPA optimizes their prompts toward the authoritative score.
    Reads best-so-far errors from each record's ``extra`` (monotone non-increasing).
    """
    items = sorted(records, key=lambda r: r.iteration)
    fig, ax = plt.subplots(figsize=(7, 4.5))

    series = [
        ("react_error", "React agent", "#2e9e54", "o"),
        ("osint_error", "OSINT agent", "#e8a13a", "s"),
        ("blended_error", "Blended final", "#233027", "^"),
    ]
    plotted = False
    for key, label, color, marker in series:
        pts = [
            (r.iteration, r.extra.get(key))
            for r in items
            if isinstance(r.extra, dict) and r.extra.get(key) is not None
        ]
        if pts:
            xs, ys = zip(*pts)
            ax.plot(xs, ys, marker=marker, color=color, label=label, linewidth=2)
            plotted = True

    ax.set_xlabel("GEPA iteration")
    ax.set_ylabel("Gap to authoritative score (|error|, 0–100)")
    ax.set_title("Both agents converge to the authoritative score")
    ax.set_ylim(0, None)
    ax.grid(True, alpha=0.3)
    _integer_xaxis(ax)
    if plotted:
        ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return out_path


def plot_run(run_name: str, plot_dir: Path | None = None) -> list[Path]:
    """Render all figures for a run; returns the saved PNG paths. Returns [] when
    the run log is empty (e.g. no training has run yet)."""
    records = load_run(run_name)
    if not records:
        logger.warning("[plots] no records for run %r — nothing to plot", run_name)
        return []
    out_dir = plot_dir or DEFAULT_PLOT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = [
        plot_learning_curve(records, out_dir / f"{run_name}_learning_curve.png"),
        plot_reward_curve(records, out_dir / f"{run_name}_reward_curve.png"),
        plot_tool_success(records, out_dir / f"{run_name}_tool_success.png"),
    ]
    # Dual-agent runs carry per-agent errors in extra; add the convergence chart.
    if any(isinstance(r.extra, dict) and r.extra.get("react_error") is not None
           for r in records):
        saved.append(
            plot_error_decline(records, out_dir / f"{run_name}_error_decline.png")
        )
    logger.info("[plots] saved %d figure(s) to %s", len(saved), out_dir)
    return saved


if __name__ == "__main__":  # pragma: no cover - manual CLI
    import sys

    name = sys.argv[1] if len(sys.argv) > 1 else "demo"
    for p in plot_run(name):
        print("saved", p)

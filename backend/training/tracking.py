"""Iteration tracking: record each candidate's metrics so the learning curve
can be plotted, and (best-effort) mirror them to a Phoenix experiment.

Every call to ``log_iteration`` appends one row — the aggregate metrics of one
candidate on one split — to a local JSONL run log. That local log is the
reliable source the plotting script reads, so curves can always be produced
even offline.

When the Phoenix client is installed and credentials are present, the same row
is also logged to a Phoenix experiment (the sponsor-facing view); failures
there are swallowed so training never depends on the network.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_RUNLOG_DIR = Path(__file__).parent / "data" / "runs"


@dataclass
class IterationRecord:
    """One learning-curve datapoint: a candidate's metrics on a split."""

    run_name: str
    iteration: int
    split_name: str
    accuracy: float | None = None
    mean_score: float | None = None
    mean_tool_success: float | None = None
    n: int = 0
    ts: float = field(default_factory=time.time)
    extra: dict = field(default_factory=dict)


def _runlog_path(run_name: str, runlog_dir: Path | None = None) -> Path:
    d = runlog_dir or DEFAULT_RUNLOG_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{run_name}.jsonl"


def log_iteration(
    record: IterationRecord,
    *,
    runlog_dir: Path | None = None,
    mirror_to_phoenix: bool = True,
) -> Path:
    """Append one iteration record to the local run log; optionally mirror to a
    Phoenix experiment. Returns the run-log path. Never raises on the Phoenix
    side — local logging is the source of truth."""
    path = _runlog_path(record.run_name, runlog_dir)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(record)) + "\n")

    if mirror_to_phoenix:
        _mirror_to_phoenix(record)
    return path


def load_run(run_name: str, runlog_dir: Path | None = None) -> list[IterationRecord]:
    """Read back a run's iteration records (for plotting)."""
    path = _runlog_path(run_name, runlog_dir)
    if not path.exists():
        return []
    records: list[IterationRecord] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(IterationRecord(**json.loads(line)))
    return records


def _mirror_to_phoenix(record: IterationRecord) -> None:
    """Best-effort mirror of one record to a Phoenix experiment. No-op when the
    client isn't installed or credentials are absent."""
    try:
        from phoenix.client import Client  # type: ignore
    except Exception:
        logger.debug("[track] phoenix client not installed; local log only")
        return
    try:
        client = Client()
        # Phoenix experiments are keyed by dataset; we log the iteration metrics
        # as experiment metadata under the run name. Kept defensive: any API
        # shape mismatch is swallowed so training is never blocked.
        client.log_experiment_evaluation(  # type: ignore[attr-defined]
            experiment_name=record.run_name,
            evaluation_name=f"{record.split_name}_iter_{record.iteration}",
            result={
                "accuracy": record.accuracy,
                "mean_score": record.mean_score,
                "mean_tool_success": record.mean_tool_success,
            },
        )
    except Exception as exc:  # noqa: BLE001 - mirroring must never break training
        logger.debug("[track] phoenix mirror skipped: %s", exc)

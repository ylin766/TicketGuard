"""Labelled-URL dataset: schema, loader, and a deterministic stratified split.

The dataset format is fixed (teammates produce files to match it), so this
module stays small — no shape-guessing. Source of truth is a JSONL file under
``backend/training/data/``; one JSON object per line:

    {"url": "https://www.stubhub.com",       "label": "safe",  "note": "..."}
    {"url": "https://eventticketscenter.com", "label": "risky", "note": "..."}

Fields:
  * ``url``   (required) — the full URL to audit.
  * ``label`` (required) — exactly ``"safe"`` or ``"risky"`` (the ground truth).
  * ``note``  (optional) — free-text human comment; never used for training.

The split is stratified (preserves the safe/risky ratio across train/val/test)
and deterministic (seeded), so the held-out test set is identical across runs —
the prerequisite for an honest learning curve.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

logger = logging.getLogger(__name__)

Label = Literal["safe", "risky"]
VALID_LABELS: frozenset[str] = frozenset({"safe", "risky"})

# Default location teammates drop the labelled file into.
DEFAULT_DATASET_PATH = Path(__file__).parent / "data" / "labeled_urls.jsonl"

# Reproducible split: same seed -> same test set every run.
DEFAULT_SEED = 1234
DEFAULT_SPLIT = (0.6, 0.2, 0.2)  # train, val, test


@dataclass(frozen=True)
class EvalExample:
    """One labelled URL — the canonical unit the trainer and metric consume."""

    url: str
    label: Label
    note: str = ""

    @property
    def is_risky(self) -> bool:
        return self.label == "risky"


@dataclass
class DatasetSplit:
    """A stratified, deterministic partition of the labelled dataset."""

    train: list[EvalExample] = field(default_factory=list)
    val: list[EvalExample] = field(default_factory=list)
    test: list[EvalExample] = field(default_factory=list)

    def counts(self) -> dict[str, dict[str, int]]:
        """Per-split label tallies, for logging/sanity-checking a split."""
        def tally(items: list[EvalExample]) -> dict[str, int]:
            return {
                "safe": sum(1 for e in items if e.label == "safe"),
                "risky": sum(1 for e in items if e.label == "risky"),
                "total": len(items),
            }

        return {"train": tally(self.train), "val": tally(self.val), "test": tally(self.test)}


def parse_example(obj: dict, *, line_no: int | None = None) -> EvalExample:
    """Validate one record and build an :class:`EvalExample`.

    Raises ``ValueError`` on a missing/blank URL or an invalid label so a
    malformed dataset fails loudly at load time rather than silently skewing
    training.
    """
    where = f" (line {line_no})" if line_no is not None else ""
    url = (obj.get("url") or "").strip()
    if not url:
        raise ValueError(f"dataset record missing 'url'{where}: {obj!r}")
    label = (obj.get("label") or "").strip().lower()
    if label not in VALID_LABELS:
        raise ValueError(
            f"dataset record has invalid label {label!r}{where}; "
            f"must be one of {sorted(VALID_LABELS)}"
        )
    note = (obj.get("note") or "").strip()
    return EvalExample(url=url, label=label, note=note)  # type: ignore[arg-type]


def load_dataset(path: str | Path | None = None) -> list[EvalExample]:
    """Load and validate the labelled JSONL dataset.

    Blank lines and ``#`` comment lines are ignored. Raises ``FileNotFoundError``
    if the file is absent (so the infra is obviously waiting on data) and
    ``ValueError`` on any malformed record.
    """
    path = Path(path) if path else DEFAULT_DATASET_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"labelled dataset not found at {path} — drop a JSONL file there "
            "(one {'url','label','note'} object per line)."
        )

    examples: list[EvalExample] = []
    with path.open(encoding="utf-8") as fh:
        for i, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {i}: {exc}") from exc
            examples.append(parse_example(obj, line_no=i))

    if not examples:
        raise ValueError(f"dataset at {path} contains no usable records")
    logger.info("[dataset] loaded %d labelled URLs from %s", len(examples), path)
    return examples


def stratified_split(
    examples: Iterable[EvalExample],
    split: tuple[float, float, float] = DEFAULT_SPLIT,
    seed: int = DEFAULT_SEED,
) -> DatasetSplit:
    """Partition examples into train/val/test, stratified by label and seeded.

    Each label is shuffled with the same seed and sliced by the split ratios
    independently, then concatenated — so both classes keep their proportion in
    every subset and the test set is stable across runs. Tiny classes degrade
    gracefully (a label with 1–2 examples simply lands wherever the rounding
    puts it rather than erroring).
    """
    if abs(sum(split) - 1.0) > 1e-6:
        raise ValueError(f"split ratios must sum to 1.0, got {split}")
    train_frac, val_frac, _ = split

    by_label: dict[str, list[EvalExample]] = {"safe": [], "risky": []}
    for ex in examples:
        by_label[ex.label].append(ex)

    result = DatasetSplit()
    rng = random.Random(seed)
    for label, items in by_label.items():
        shuffled = items[:]
        rng.shuffle(shuffled)
        n = len(shuffled)
        n_train = int(n * train_frac)
        n_val = int(n * val_frac)
        result.train.extend(shuffled[:n_train])
        result.val.extend(shuffled[n_train:n_train + n_val])
        result.test.extend(shuffled[n_train + n_val:])

    # Shuffle the concatenated subsets so labels aren't grouped, still seeded.
    for subset in (result.train, result.val, result.test):
        rng.shuffle(subset)

    logger.info("[dataset] split counts: %s", result.counts())
    return result

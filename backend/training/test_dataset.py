"""Tests for the labelled-URL dataset loader and stratified split. Offline:
uses tmp_path JSONL files, no network."""

import json

import pytest

from backend.training.dataset import (
    DEFAULT_SEED,
    EvalExample,
    load_dataset,
    parse_example,
    stratified_split,
)


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# parse_example                                                               #
# --------------------------------------------------------------------------- #

def test_parse_example_valid():
    ex = parse_example({"url": "https://x.com", "label": "safe", "note": "ok"})
    assert ex.url == "https://x.com"
    assert ex.label == "safe"
    assert ex.note == "ok"
    assert ex.is_risky is False


def test_parse_example_label_normalized():
    ex = parse_example({"url": "https://x.com", "label": "RISKY"})
    assert ex.label == "risky"
    assert ex.is_risky is True


def test_parse_example_missing_url_raises():
    with pytest.raises(ValueError):
        parse_example({"label": "safe"})


def test_parse_example_bad_label_raises():
    with pytest.raises(ValueError):
        parse_example({"url": "https://x.com", "label": "maybe"})


# --------------------------------------------------------------------------- #
# load_dataset                                                                #
# --------------------------------------------------------------------------- #

def test_load_dataset_skips_blank_and_comments(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text(
        "# header comment\n"
        '{"url": "https://a.com", "label": "safe"}\n'
        "\n"
        '{"url": "https://b.com", "label": "risky"}\n',
        encoding="utf-8",
    )
    examples = load_dataset(p)
    assert len(examples) == 2
    assert {e.url for e in examples} == {"https://a.com", "https://b.com"}


def test_load_dataset_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_dataset(tmp_path / "nope.jsonl")


def test_load_dataset_bad_json_raises(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text('{"url": "https://a.com", "label": "safe"}\n{bad json}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_dataset(p)


def test_load_dataset_empty_raises(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text("# only comments\n\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_dataset(p)


# --------------------------------------------------------------------------- #
# stratified_split                                                            #
# --------------------------------------------------------------------------- #

def _make(n_safe, n_risky):
    return (
        [EvalExample(f"https://safe{i}.com", "safe") for i in range(n_safe)]
        + [EvalExample(f"https://risky{i}.com", "risky") for i in range(n_risky)]
    )


def test_split_ratios_and_no_leakage():
    examples = _make(10, 10)
    split = stratified_split(examples, split=(0.6, 0.2, 0.2), seed=DEFAULT_SEED)
    # All examples accounted for exactly once (no leakage, no loss).
    all_urls = [e.url for e in split.train + split.val + split.test]
    assert len(all_urls) == 20
    assert len(set(all_urls)) == 20


def test_split_is_stratified():
    examples = _make(10, 10)
    split = stratified_split(examples, split=(0.6, 0.2, 0.2))
    c = split.counts()
    # 60/20/20 of 10 per class = 6/2/2 each.
    assert c["train"]["safe"] == 6 and c["train"]["risky"] == 6
    assert c["test"]["safe"] == 2 and c["test"]["risky"] == 2


def test_split_is_deterministic():
    examples = _make(8, 8)
    a = stratified_split(examples, seed=42)
    b = stratified_split(examples, seed=42)
    assert [e.url for e in a.test] == [e.url for e in b.test]


def test_split_different_seeds_differ():
    examples = _make(20, 20)
    a = stratified_split(examples, seed=1)
    b = stratified_split(examples, seed=2)
    assert [e.url for e in a.test] != [e.url for e in b.test]


def test_split_ratios_must_sum_to_one():
    with pytest.raises(ValueError):
        stratified_split(_make(2, 2), split=(0.5, 0.4, 0.4))

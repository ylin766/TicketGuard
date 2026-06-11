"""Tests for the batch runner and the GEPA-loop's evaluation core. Fully
offline: a stub AuditFn returns canned audit dicts, so no LLM, no network, and
GEPA itself is never imported (it's lazy in gepa_loop)."""

import asyncio

import pytest

from backend.training.dataset import EvalExample
from backend.training.gepa_loop import OSINT_COMPONENT, evaluate_candidate
from backend.training.runner import run_example, run_split


def _audit_for(score_by_url):
    """Build a stub AuditFn that returns a fixed score per URL."""
    async def audit_fn(url, candidate):
        return {"url": url, "score": score_by_url[url]}
    return audit_fn


def _raising_audit():
    async def audit_fn(url, candidate):
        raise RuntimeError("boom")
    return audit_fn


# --------------------------------------------------------------------------- #
# run_example                                                                 #
# --------------------------------------------------------------------------- #

def test_run_example_correct():
    ex = EvalExample("https://a.com", "risky")
    audit_fn = _audit_for({"https://a.com": 10})
    r = asyncio.run(run_example(ex, {}, audit_fn, threshold=50))
    assert r.correct is True
    assert r.predicted_label == "risky"


def test_run_example_audit_failure_is_zero():
    ex = EvalExample("https://a.com", "safe")
    r = asyncio.run(run_example(ex, {}, _raising_audit(), threshold=50))
    assert r.score == 0.0
    assert r.correct is False
    assert "AUDIT ERROR" in r.feedback


def test_run_example_judge_failure_is_tolerated():
    ex = EvalExample("https://a.com", "risky")
    audit_fn = _audit_for({"https://a.com": 10})

    def bad_judge(audit):
        raise RuntimeError("judge down")

    # Should still score on correctness alone, not raise.
    r = asyncio.run(run_example(ex, {}, audit_fn, threshold=50, judge_fn=bad_judge))
    assert r.correct is True


# --------------------------------------------------------------------------- #
# run_split                                                                   #
# --------------------------------------------------------------------------- #

def test_run_split_aggregates():
    examples = [
        EvalExample("https://a.com", "risky"),
        EvalExample("https://b.com", "safe"),
        EvalExample("https://c.com", "safe"),
    ]
    audit_fn = _audit_for({
        "https://a.com": 10,   # correct risky
        "https://b.com": 90,   # correct safe
        "https://c.com": 10,   # wrong (predicts risky, truth safe)
    })
    results, summary = asyncio.run(run_split(examples, {}, audit_fn, threshold=50))
    assert len(results) == 3
    assert summary["n"] == 3
    assert summary["accuracy"] == round(2 / 3, 4)


# --------------------------------------------------------------------------- #
# evaluate_candidate (gepa_loop, GEPA not imported)                           #
# --------------------------------------------------------------------------- #

def test_evaluate_candidate_returns_iteration_result():
    split = [
        EvalExample("https://a.com", "risky"),
        EvalExample("https://b.com", "safe"),
    ]
    audit_fn = _audit_for({"https://a.com": 5, "https://b.com": 95})
    res = asyncio.run(
        evaluate_candidate(
            {OSINT_COMPONENT: "p"}, split, audit_fn,
            split_name="val", iteration=3, threshold=50,
        )
    )
    assert res.iteration == 3
    assert res.split_name == "val"
    assert res.summary["accuracy"] == 1.0
    assert res.candidate[OSINT_COMPONENT] == "p"


def test_seed_candidate_loads_real_prompt():
    from backend.training.gepa_loop import seed_candidate

    seed = seed_candidate()
    assert OSINT_COMPONENT in seed
    assert isinstance(seed[OSINT_COMPONENT], str)
    assert len(seed[OSINT_COMPONENT]) > 0

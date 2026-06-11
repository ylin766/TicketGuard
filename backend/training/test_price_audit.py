"""Tests for the price agent's judge-only training path. Offline: judge output
is injected as dicts and the AuditFn runs against a stub snapshot provider, so
no LLM / browser / network is touched."""

import asyncio

from backend.training.dataset import EvalExample
from backend.training.metric import score_judge_only
from backend.training.price_audit import (
    PRICE_EVAL_COMPONENT,
    PRICE_EXTRACT_COMPONENT,
    assemble_price_audit,
    make_price_audit_fn,
    price_seed_candidate,
    price_snapshot,
)
from backend.training.runner import run_example


# --------------------------------------------------------------------------- #
# score_judge_only (no ground truth)                                          #
# --------------------------------------------------------------------------- #

def test_score_judge_only_blends_judge_and_tools():
    audit = {"agent_audit": {"stats": {"tool_calls": 2, "tool_successes": 1}}}
    judged = {
        "price_reasonableness": {"score": 1.0, "explanation": "coherent and grounded"},
    }
    r = score_judge_only(audit, judged)
    # judge 1.0 (w .8) + tool .5 (w .2) -> (.8 + .1)/1.0 = .9
    assert r.score == 0.9
    assert r.correct is None  # never a correctness comparison
    assert r.predicted_label is None
    assert "coherent and grounded" in r.feedback


def test_score_judge_only_judge_missing_falls_back_to_tools():
    audit = {"agent_audit": {"stats": {"tool_calls": 4, "tool_successes": 4}}}
    r = score_judge_only(audit, {})
    assert r.score == 1.0  # only tool success present
    assert r.components["judge"] is None


def test_score_judge_only_no_signal_is_zero():
    r = score_judge_only({}, {})
    assert r.score == 0.0


# --------------------------------------------------------------------------- #
# assemble_price_audit / snapshot                                             #
# --------------------------------------------------------------------------- #

def test_assemble_price_audit_shape():
    result = {
        "user_listing": {"price_per_ticket": 200},
        "stats": {"percentile": 80, "median": 150},
        "analysis": {"verdict": "overpriced"},
    }
    audit = assemble_price_audit("https://x.com", result, tool_calls=1, tool_successes=1)
    assert audit["analysis"]["verdict"] == "overpriced"
    assert audit["agent_audit"]["stats"]["tool_successes"] == 1
    snap = price_snapshot(audit)
    assert snap["stats"]["percentile"] == 80


def test_price_seed_candidate_is_eval_only():
    # Extraction is not trained offline; only the eval prompt is optimized.
    seed = price_seed_candidate()
    assert PRICE_EVAL_COMPONENT in seed
    assert PRICE_EXTRACT_COMPONENT not in seed
    assert "{stats}" in seed[PRICE_EVAL_COMPONENT]


# --------------------------------------------------------------------------- #
# make_price_audit_fn with stub snapshot (no scrape) + run_example judge_only  #
# --------------------------------------------------------------------------- #

def test_price_audit_fn_empty_scrape_is_failure():
    # snapshot provider returns no listings -> tool failure, empty analysis
    def provider(url):
        return None, []

    audit_fn = make_price_audit_fn(provider)
    audit = asyncio.run(audit_fn("https://x.com", price_seed_candidate()))
    assert audit["agent_audit"]["stats"]["tool_successes"] == 0


def test_run_example_judge_only_path():
    # A price audit scored judge-only via an injected judge_fn.
    def provider(url):
        return None, []

    audit_fn = make_price_audit_fn(provider)

    def judge_fn(audit):
        return {"price_reasonableness": {"score": 0.5}}

    r = asyncio.run(run_example(
        EvalExample("https://x.com", "safe"),  # label ignored in judge_only
        price_seed_candidate(), audit_fn,
        threshold=50, judge_fn=judge_fn, judge_only=True,
    ))
    assert r.correct is None
    assert r.components["judge"] is not None

"""Tests for the GEPA-compatible audit metric. Fully offline: judge output is
passed in as a dict, so no LLM is ever constructed."""

from backend.training.metric import (
    DEFAULT_SAFE_THRESHOLD,
    aggregate_metrics,
    predict_label,
    score_audit,
    tool_success_rate,
)


# --------------------------------------------------------------------------- #
# predict_label                                                               #
# --------------------------------------------------------------------------- #

def test_predict_label_threshold():
    assert predict_label(90) == "safe"
    assert predict_label(10) == "risky"
    assert predict_label(DEFAULT_SAFE_THRESHOLD) == "safe"
    assert predict_label(DEFAULT_SAFE_THRESHOLD - 1) == "risky"


def test_predict_label_custom_threshold():
    assert predict_label(60, threshold=70) == "risky"
    assert predict_label(70, threshold=70) == "safe"


def test_predict_label_none_abstains():
    assert predict_label(None) is None


# --------------------------------------------------------------------------- #
# tool_success_rate                                                           #
# --------------------------------------------------------------------------- #

def test_tool_success_from_successes():
    assert tool_success_rate({"stats": {"tool_calls": 4, "tool_successes": 3}}) == 0.75


def test_tool_success_from_failures():
    assert tool_success_rate({"stats": {"tool_calls": 4, "tool_failures": 1}}) == 0.75


def test_tool_success_flat_shape():
    assert tool_success_rate({"tool_calls": 2, "tool_successes": 2}) == 1.0


def test_tool_success_unknown_returns_none():
    assert tool_success_rate({"stats": {"tool_calls": 0}}) is None
    assert tool_success_rate({}) is None
    assert tool_success_rate(None) is None


# --------------------------------------------------------------------------- #
# score_audit                                                                 #
# --------------------------------------------------------------------------- #

def test_score_audit_correct_risky():
    audit = {"score": 15}
    r = score_audit(audit, "risky")
    assert r.predicted_label == "risky"
    assert r.correct is True
    assert r.score == 1.0  # only correctness present -> full
    assert "CORRECT" in r.feedback


def test_score_audit_wrong_gives_diagnostic():
    audit = {"score": 90}  # predicts safe
    r = score_audit(audit, "risky")
    assert r.correct is False
    assert r.score == 0.0
    assert "WRONG" in r.feedback and "Missed a risky site" in r.feedback


def test_score_audit_blends_tool_success():
    # correct (1.0) + tool success 0.5; weights correctness .6, tool .2
    audit = {"score": 10, "agent_audit": {"stats": {"tool_calls": 2, "tool_successes": 1}}}
    r = score_audit(audit, "risky")
    # present weights: correctness .6, tool_success .2 -> (.6*1 + .2*.5)/.8 = .875
    assert r.score == 0.875
    assert r.components["tool_success"] == 0.5


def test_score_audit_blends_judge():
    audit = {"score": 10}
    judged = {
        "evidence_grounding": {"score": 1.0, "explanation": "well supported"},
        "consistency": {"score": 1.0},
        "routing_efficiency": {"score": 1.0},
    }
    r = score_audit(audit, "risky", judged=judged)
    # correctness 1.0 (w .6) + judge 1.0 (w .2) -> (.6+.2)/.8 = 1.0
    assert r.score == 1.0
    assert r.components["judge"] == 1.0
    assert "well supported" in r.feedback


def test_score_audit_abstain_when_no_score():
    r = score_audit({}, "safe")
    assert r.predicted_label is None
    assert r.correct is None
    assert "ABSTAINED" in r.feedback


def test_score_audit_as_gepa_shape():
    r = score_audit({"score": 15}, "risky")
    g = r.as_gepa()
    assert set(g) == {"score", "feedback"}
    assert isinstance(g["score"], float)


# --------------------------------------------------------------------------- #
# aggregate_metrics                                                           #
# --------------------------------------------------------------------------- #

def test_aggregate_metrics():
    results = [
        score_audit({"score": 15}, "risky"),   # correct
        score_audit({"score": 90}, "safe"),     # correct
        score_audit({"score": 90}, "risky"),    # wrong
    ]
    agg = aggregate_metrics(results)
    assert agg["n"] == 3
    assert agg["accuracy"] == round(2 / 3, 4)


def test_aggregate_metrics_empty():
    agg = aggregate_metrics([])
    assert agg["n"] == 0
    assert agg["accuracy"] == 0.0

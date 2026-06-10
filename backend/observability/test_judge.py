"""Tests for the LLM-as-judge reward channel. These run fully offline — no
phoenix.evals LLM is constructed and no network is touched; evaluators are
faked so we only test our own snapshot/aggregation/degradation logic."""

import backend.observability.judge as judge


# --------------------------------------------------------------------------- #
# Fakes                                                                       #
# --------------------------------------------------------------------------- #

class _FakeScore:
    def __init__(self, score, label, explanation):
        self.score = score
        self.label = label
        self.explanation = explanation


class _FakeEvaluator:
    """Stands in for a phoenix ClassificationEvaluator without any LLM call."""

    def __init__(self, name, score, label, explanation="because"):
        self.name = name
        self._payload = (score, label, explanation)

    def evaluate(self, eval_input, input_mapping=None):
        return [_FakeScore(*self._payload)]


class _RaisingEvaluator:
    name = "routing_efficiency"

    def evaluate(self, eval_input, input_mapping=None):
        raise RuntimeError("provider down")


# --------------------------------------------------------------------------- #
# summarize_evidence / snapshot                                               #
# --------------------------------------------------------------------------- #

def test_summarize_evidence_lists_sources():
    pr = {
        "sources": [
            {"name": "VirusTotal", "threat": True, "detail": "5/90 engines"},
            {"name": "Tranco", "threat": False, "detail": "rank 1200"},
        ]
    }
    text = judge.summarize_evidence(pr)
    assert "VirusTotal" in text and "THREAT" in text
    assert "Tranco" in text and "clean" in text


def test_summarize_evidence_falls_back_to_top_level():
    text = judge.summarize_evidence({"flagged": True, "status": "ok"})
    assert "flagged" in text and "status" in text


def test_summarize_evidence_handles_non_dict():
    assert judge.summarize_evidence(None) == "(no evidence available)"


def test_build_snapshot_extracts_fields():
    result = {
        "run_id": "abc",
        "url": "http://x.com",
        "score": 42,
        "risk_level": "High Risk",
        "grey_zone": True,
        "agent_audit": {"report": "found scam reports"},
        "sources": [{"name": "VT", "threat": True, "detail": "bad"}],
    }
    snap = judge.build_snapshot(result)
    assert snap["run_id"] == "abc"
    assert snap["score"] == 42
    assert snap["grey_zone"] is True
    assert snap["agent_ran"] is True
    assert "found scam reports" in snap["agent_report"]
    assert "VT" in snap["evidence"]


def test_build_snapshot_no_agent():
    snap = judge.build_snapshot({"score": 90, "risk_level": "safe"})
    assert snap["agent_ran"] is False
    assert snap["agent_report"] == "(no agent report)"


# --------------------------------------------------------------------------- #
# judge_audit with injected fake evaluators                                   #
# --------------------------------------------------------------------------- #

def test_judge_audit_collects_all_dimensions():
    evaluators = [
        _FakeEvaluator("evidence_grounding", 1.0, "grounded"),
        _FakeEvaluator("consistency", 0.5, "minor_inconsistency"),
        _FakeEvaluator("routing_efficiency", 0.3, "wasteful"),
    ]
    out = judge.judge_audit({"score": 80}, evaluators=evaluators)
    assert set(out) == {"evidence_grounding", "consistency", "routing_efficiency"}
    assert out["evidence_grounding"]["label"] == "grounded"
    assert out["evidence_grounding"]["score"] == 1.0


def test_judge_audit_skips_failing_dimension():
    evaluators = [
        _FakeEvaluator("evidence_grounding", 1.0, "grounded"),
        _RaisingEvaluator(),
    ]
    out = judge.judge_audit({"score": 80}, evaluators=evaluators)
    assert "evidence_grounding" in out
    assert "routing_efficiency" not in out  # the raising one is skipped


def test_judge_audit_empty_when_no_evaluators():
    assert judge.judge_audit({"score": 50}, evaluators=[]) == {}


# --------------------------------------------------------------------------- #
# aggregate_reward                                                            #
# --------------------------------------------------------------------------- #

def test_aggregate_reward_weighted_average():
    judged = {
        "evidence_grounding": {"score": 1.0},
        "consistency": {"score": 1.0},
        "routing_efficiency": {"score": 1.0},
    }
    assert judge.aggregate_reward(judged) == 1.0


def test_aggregate_reward_renormalizes_partial():
    # Only grounding present -> reward equals that score regardless of its weight.
    judged = {"evidence_grounding": {"score": 0.5}}
    assert judge.aggregate_reward(judged) == 0.5


def test_aggregate_reward_mixed():
    judged = {
        "evidence_grounding": {"score": 1.0},   # w 0.5
        "consistency": {"score": 0.0},          # w 0.3
        "routing_efficiency": {"score": 0.0},   # w 0.2
    }
    # (0.5*1 + 0.3*0 + 0.2*0) / (0.5+0.3+0.2) = 0.5
    assert judge.aggregate_reward(judged) == 0.5


def test_aggregate_reward_none_when_empty():
    assert judge.aggregate_reward({}) is None
    assert judge.aggregate_reward({"x": {"score": None}}) is None


def test_reward_weights_match_evaluator_names():
    """Guard against a dimension name drifting between the rubric specs and the
    reward weights — a silent way to drop a reward component."""
    spec_names = {name for name, _, _ in judge._EVALUATOR_SPECS}
    assert spec_names == set(judge.REWARD_WEIGHTS)

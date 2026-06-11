"""Tests for the pure helpers in the real AuditFn. Offline: the LLM-bound
run_osint_audit is not exercised; only classification and result shaping are."""

from backend.training.audit_fn import assemble_audit, classify_tool_result


# --------------------------------------------------------------------------- #
# classify_tool_result                                                        #
# --------------------------------------------------------------------------- #

def test_classify_usable_content():
    assert classify_tool_result("Found 12 reviews on Trustpilot, avg 2.1 stars") is True


def test_classify_empty_is_failure():
    assert classify_tool_result("") is False
    assert classify_tool_result("   ") is False
    assert classify_tool_result(None) is False


def test_classify_403_is_failure():
    assert classify_tool_result("HTTP 403 Forbidden") is False


def test_classify_captcha_is_failure():
    assert classify_tool_result("Please complete the captcha to continue") is False


def test_classify_no_results_is_failure():
    assert classify_tool_result("No results found for query") is False


def test_classify_exception_is_failure():
    assert classify_tool_result("Exception: connection reset") is False


# --------------------------------------------------------------------------- #
# assemble_audit                                                              #
# --------------------------------------------------------------------------- #

def test_assemble_audit_shape():
    report = {"score": 15, "tier": "Critical Risk", "text": "report body"}
    audit = assemble_audit(
        "https://x.com", report,
        tool_calls=5, tool_successes=3,
        prompt_tokens=100, completion_tokens=50, total_tokens=150,
        duration_ms=2200,
    )
    assert audit["url"] == "https://x.com"
    assert audit["score"] == 15
    assert audit["risk_level"] == "Critical Risk"
    stats = audit["agent_audit"]["stats"]
    assert stats["tool_calls"] == 5
    assert stats["tool_successes"] == 3
    assert stats["tool_failures"] == 2
    assert stats["total_tokens"] == 150


def test_assemble_audit_feeds_metric_tool_success():
    """The assembled audit must be readable by metric.tool_success_rate."""
    from backend.training.metric import tool_success_rate

    report = {"score": 80, "tier": "Generally Safe", "text": ""}
    audit = assemble_audit(
        "https://x.com", report,
        tool_calls=4, tool_successes=3,
        prompt_tokens=0, completion_tokens=0, total_tokens=0, duration_ms=0,
    )
    assert tool_success_rate(audit["agent_audit"]) == 0.75


def test_assemble_audit_none_score():
    report = {"score": None, "tier": None, "text": ""}
    audit = assemble_audit(
        "https://x.com", report,
        tool_calls=0, tool_successes=0,
        prompt_tokens=0, completion_tokens=0, total_tokens=0, duration_ms=0,
    )
    assert audit["score"] is None

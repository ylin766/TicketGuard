"""Tests for the trace helper layer that turns each audit into an RL-ready
trace. These must run without real Phoenix credentials and never hit the
network — attribute mapping is verified against a fake span."""

import backend.observability.trace_utils as tu


class _FakeSpan:
    """Records set_attribute calls so we can assert what got written."""

    def __init__(self):
        self.attrs: dict = {}

    def set_attribute(self, key, value):
        self.attrs[key] = value


def test_new_run_id_is_unique_hex():
    a = tu.new_run_id()
    b = tu.new_run_id()
    assert a != b
    assert len(a) == 32
    int(a, 16)  # raises if not valid hex


def test_audit_span_never_raises_and_is_context_manager():
    """Whether or not an OTel SDK is active, audit_span must be usable as a
    context manager and never raise on the request path."""
    rid = tu.new_run_id()
    with tu.audit_span("http://example.com", rid) as span:
        # span is either a live span or None (tracing disabled) — both fine.
        tu.set_audit_result(span, score=50)


def test_set_audit_result_none_span_is_noop():
    """A None span (tracing disabled) must be silently ignored."""
    tu.set_audit_result(None, score=10, risk_level="High Risk", grey_zone=True)


def test_set_audit_result_maps_all_fields():
    span = _FakeSpan()
    tu.set_audit_result(
        span,
        score=42,
        risk_level="Mixed Reliability",
        grey_zone=True,
        agent_ran=False,
        flagged=True,
        status="ok",
        latency_ms=123,
        agent_tokens=4567,
    )
    assert span.attrs[tu.ATTR_SCORE] == 42
    assert span.attrs[tu.ATTR_RISK_LEVEL] == "Mixed Reliability"
    assert span.attrs[tu.ATTR_GREY_ZONE] is True
    assert span.attrs[tu.ATTR_AGENT_RAN] is False
    assert span.attrs[tu.ATTR_FLAGGED] is True
    assert span.attrs[tu.ATTR_STATUS] == "ok"
    assert span.attrs[tu.ATTR_LATENCY_MS] == 123
    assert span.attrs[tu.ATTR_AGENT_TOKENS] == 4567
    # A derived human-readable verdict is set when score is present.
    assert "42" in span.attrs[tu.ATTR_OUTPUT_VALUE]


def test_set_audit_result_skips_none_fields():
    """None-valued fields must not be written, so partial results (e.g. a
    pipeline-only run) don't pollute the span with empty attributes."""
    span = _FakeSpan()
    tu.set_audit_result(span, score=None, agent_tokens=None, status="ok")
    assert tu.ATTR_SCORE not in span.attrs
    assert tu.ATTR_AGENT_TOKENS not in span.attrs
    assert tu.ATTR_STATUS in span.attrs
    # No score -> no derived verdict.
    assert tu.ATTR_OUTPUT_VALUE not in span.attrs


def test_set_audit_result_verdict_includes_risk_when_present():
    span = _FakeSpan()
    tu.set_audit_result(span, score=15, risk_level="Critical Risk")
    verdict = span.attrs[tu.ATTR_OUTPUT_VALUE]
    assert "15" in verdict
    assert "Critical Risk" in verdict

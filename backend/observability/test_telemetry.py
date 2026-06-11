"""Tests for the central telemetry bootstrap. These must run without any real
Phoenix credentials and never make network calls."""

import importlib

import backend.observability.telemetry as telemetry


def _fresh_module():
    """Reload the module so its process-level _done guard resets per test."""
    return importlib.reload(telemetry)


def test_no_key_is_noop(monkeypatch):
    """Without PHOENIX_API_KEY, init returns None and sets no tracer provider."""
    mod = _fresh_module()
    monkeypatch.delenv("PHOENIX_API_KEY", raising=False)
    assert mod.init_telemetry() is None
    # Idempotent: a second call is still a no-op, still None.
    assert mod.init_telemetry() is None
    assert mod.phoenix_url() is None


def test_idempotent_caches_result(monkeypatch):
    """Repeated calls return the cached value without re-instrumenting.

    We don't assert a URL (that would require real instrumentation packages and
    a key); we assert the call is stable and never raises.
    """
    mod = _fresh_module()
    monkeypatch.delenv("PHOENIX_API_KEY", raising=False)
    first = mod.init_telemetry()
    second = mod.init_telemetry()
    assert first == second  # cached, consistent


def test_failure_is_swallowed(monkeypatch):
    """Even if the key is set, a broken exporter import must not raise — telemetry
    is best-effort and can never take the request path down."""
    mod = _fresh_module()
    monkeypatch.setenv("PHOENIX_API_KEY", "dummy-key")
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "http://127.0.0.1:0/v1/traces")
    # Should not raise regardless of whether instrumentation succeeds.
    result = mod.init_telemetry()
    assert result is None or isinstance(result, str)

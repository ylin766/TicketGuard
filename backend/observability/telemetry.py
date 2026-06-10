"""Central telemetry bootstrap for TicketGuard.

A single, idempotent place that wires Arize Phoenix / OpenTelemetry tracing for
every LLM-calling path in the backend — not just the OSINT stream. Initializing
the instrumentors once at process startup means traces are emitted no matter
which entry point invokes an agent:

  * ADK agents (OSINT subagent, browser-check ReAct explorer) — captured by
    ``GoogleADKInstrumentor``.
  * Direct ``google.genai`` calls (browser-check's vision JSON extraction in
    ``llm/gemini_client.py``) — captured by ``GoogleGenAIInstrumentor`` when the
    optional ``openinference-instrumentation-google-genai`` package is present.

Tracing is best-effort: missing credentials or instrumentation packages never
break the app — failures are swallowed and logged.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = "https://app.phoenix.arize.com/s/linyushuhong/v1/traces"

# Module-level guard so init runs at most once per process.
_done = False
_phoenix_url: str | None = None


def init_telemetry() -> str | None:
    """Enable Phoenix tracing once per process. Returns the Phoenix workspace
    URL (for deep-linking from the UI) or ``None`` when tracing is disabled.

    Idempotent: subsequent calls return the cached URL without re-instrumenting.
    Safe to call from anywhere — all failures are caught so telemetry can never
    take the request path down.
    """
    global _done, _phoenix_url

    if _done:
        return _phoenix_url

    api_key = os.environ.get("PHOENIX_API_KEY")
    endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", _DEFAULT_ENDPOINT)
    if not api_key:
        _done = True
        logger.info("[telemetry] PHOENIX_API_KEY not set — tracing disabled")
        return None

    try:
        from opentelemetry import trace as _trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(exporter))
        _trace.set_tracer_provider(provider)

        # ADK agents (OSINT subagent + browser-check ReAct explorer).
        try:
            from openinference.instrumentation.google_adk import (
                GoogleADKInstrumentor,
            )

            GoogleADKInstrumentor().instrument(tracer_provider=provider)
            logger.info("[telemetry] GoogleADKInstrumentor enabled")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[telemetry] ADK instrumentation unavailable: %s", exc)

        # Direct google.genai calls (browser-check vision JSON extraction).
        try:
            from openinference.instrumentation.google_genai import (
                GoogleGenAIInstrumentor,
            )

            GoogleGenAIInstrumentor().instrument(tracer_provider=provider)
            logger.info("[telemetry] GoogleGenAIInstrumentor enabled")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[telemetry] GenAI instrumentation unavailable: %s", exc)

        _phoenix_url = endpoint.replace("/v1/traces", "")
        logger.info("[telemetry] Phoenix tracing enabled → %s", endpoint)
    except Exception as exc:  # noqa: BLE001 - tracing must never break the app
        logger.warning("[telemetry] setup failed, continuing without tracing: %s", exc)
        _phoenix_url = None
    finally:
        _done = True

    return _phoenix_url


def phoenix_url() -> str | None:
    """Return the Phoenix workspace URL if telemetry is active, else None."""
    return _phoenix_url

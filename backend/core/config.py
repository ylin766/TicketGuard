"""Shared configuration for the TicketGuard backend."""

import os

# Gemini model used by every agent. Override via the GEMINI_MODEL env var.
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# GCP project for ADC-based authentication (API keys are disallowed by org policy).
# Set GOOGLE_CLOUD_PROJECT env var or fill in the .env file.
GOOGLE_CLOUD_PROJECT: str = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
GOOGLE_CLOUD_LOCATION: str = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

# Hard cap for any outbound HTTP request (seconds).
HTTP_TIMEOUT_SECONDS: int = 15


def build_gemini_model(model: str | None = None):
    """Return an ADK ``Gemini`` model wired with exponential-backoff retries.

    Vertex AI enforces a per-minute quota on the shared model. One audit fans out
    into many concurrent LLM calls (the OSINT ReAct agent's multi-step loop, the
    Layer-2 browse explorer, price analysis, the judge), so a transient
    ``429 RESOURCE_EXHAUSTED`` is expected under load. Passing the model as a
    configured ``Gemini`` instance (instead of a bare string) lets the genai
    client retry 429/5xx with backoff — riding over the quota window — which is
    exactly the mitigation Google's 429 docs recommend, instead of failing the
    whole agent node on the first burst.
    """
    from google.adk.models.google_llm import Gemini
    from google.genai import types as genai_types

    return Gemini(
        model=model or GEMINI_MODEL,
        retry_options=genai_types.HttpRetryOptions(
            attempts=5,
            initial_delay=2.0,
            max_delay=60.0,
            exp_base=2.0,
            # Retry quota exhaustion (429) and transient server errors.
            http_status_codes=[429, 500, 502, 503, 504],
        ),
    )

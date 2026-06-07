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

"""Shared configuration for the TicketGuard backend."""

import os

# Gemini model used by every agent. Override via the GEMINI_MODEL env var.
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Hard cap for any outbound HTTP request (seconds).
HTTP_TIMEOUT_SECONDS: int = 15

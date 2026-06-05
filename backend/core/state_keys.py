"""Cross-feature contract: session state keys.

This is the ONLY thing the three feature owners must agree on:
- preprocess writes the page once (PAGE_*).
- each feature reads the page and writes its own result (*_RESULT).

Each ``*_RESULT`` value is a feature-specific dict. The security feature writes:
    {"status": str, "findings": list[dict], "flagged": bool, "detail": str}
where each finding is one threat-intel source's native report.
"""

# --- written by preprocess ---
PAGE_URL = "page_url"
PAGE_HTML = "page_html"
PAGE_SCREENSHOT = "page_screenshot"  # optional (filesystem path)

# --- written by each feature ---
SEAT_RESULT = "seat_result"
PRICE_RESULT = "price_result"
SECURITY_RESULT = "security_result"

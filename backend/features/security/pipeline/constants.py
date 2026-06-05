"""Constants for the security pipeline (detectors + weighted scoring)."""

# --- Environment variable names (never hardcode secrets) ---
INTELOWL_URL_ENV = "INTELOWL_URL"
INTELOWL_TOKEN_ENV = "INTELOWL_API_KEY"
SPIDERFOOT_URL_ENV = "SPIDERFOOT_URL"

# --- IntelOwl ---
INTELOWL_PLAYBOOK = "FREE_TO_USE_ANALYZERS"
INTELOWL_MAX_WAIT_SECONDS = 90

# --- SpiderFoot ---
SPIDERFOOT_DEFAULT_URL = "http://localhost:5001"
SPIDERFOOT_USECASE = "investigate"
SPIDERFOOT_MAX_WAIT_SECONDS = 120
# SpiderFoot event types that indicate a threat signal.
SPIDERFOOT_MALICIOUS_PREFIXES = ("MALICIOUS_", "BLACKLISTED_")

# --- Polling (shared) ---
DETECTOR_POLL_INTERVAL_SECONDS = 5

# --- Weighted scoring ---
# IntelOwl aggregates curated analyzers (VirusTotal, Phishtank, URLhaus, Safe
# Browsing) so it is trusted more than SpiderFoot's broader OSINT sweep.
DETECTOR_WEIGHTS = {"intelowl": 0.6, "spiderfoot": 0.4}

# Risk floors so a single high-confidence hit is not diluted by many benign analyzers.
RISK_FLOOR_SINGLE_HIT = 55
RISK_FLOOR_MULTI_HIT = 80

# Neutral score used when no detector is reachable.
NEUTRAL_SCORE = 50

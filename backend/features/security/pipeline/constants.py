"""Constants for the security pipeline (threat-intel sources + scoring)."""

# --- Environment variable names (never hardcode secrets) ---
# Threat-intel sources. Leave a key unset to skip that source.
VIRUSTOTAL_API_KEY_ENV = "VIRUSTOTAL_API_KEY"
SAFE_BROWSING_API_KEY_ENV = "SAFE_BROWSING_API_KEY"
URLHAUS_AUTH_KEY_ENV = "URLHAUS_AUTH_KEY"

# --- Threat-intel aggregator (online sources, no Docker) ---
VIRUSTOTAL_API_BASE = "https://www.virustotal.com/api/v3"
SAFE_BROWSING_API_URL = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
URLHAUS_API_URL = "https://urlhaus-api.abuse.ch/v1/url/"
THREATINTEL_MAX_WAIT_SECONDS = 60
DETECTOR_POLL_INTERVAL_SECONDS = 5

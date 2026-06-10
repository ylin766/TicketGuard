"""Constants for the security pipeline (threat-intel sources + scoring)."""

# --- Environment variable names (never hardcode secrets) ---
# Threat-intel sources. Leave a key unset to skip that source.
VIRUSTOTAL_API_KEY_ENV = "VIRUSTOTAL_API_KEY"
SAFE_BROWSING_API_KEY_ENV = "SAFE_BROWSING_API_KEY"
URLHAUS_AUTH_KEY_ENV = "URLHAUS_AUTH_KEY"
CHECKPHISH_API_KEY_ENV = "CHECKPHISH_API_KEY"
METADEFENDER_API_KEY_ENV = "METADEFENDER_API_KEY"

# --- Threat-intel aggregator (online sources, no Docker) ---
VIRUSTOTAL_API_BASE = "https://www.virustotal.com/api/v3"
SAFE_BROWSING_API_URL = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
URLHAUS_API_URL = "https://urlhaus-api.abuse.ch/v1/url/"
CHECKPHISH_SCAN_URL = "https://developers.checkphish.ai/api/neo/scan"
CHECKPHISH_STATUS_URL = "https://developers.checkphish.ai/api/neo/scan/status"
METADEFENDER_URL_BASE = "https://api.metadefender.com/v4/url"
SUCURI_API_URL = "https://sitecheck.sucuri.net/api/v3/"
TRANCO_API_BASE = "https://tranco-list.eu/api/ranks/domain"
# Keyless sources.
OPENPHISH_FEED_URL = "https://openphish.com/feed.txt"
OPENPHISH_CACHE_TTL_SECONDS = 3600
PHISHSTATS_API_URL = "https://api.phishstats.info/api/phishing"
CRTSH_API_URL = "https://crt.sh/"
WAYBACK_AVAILABLE_URL = "https://archive.org/wayback/available"
RDAP_API_BASE = "https://rdap.org/domain"
DNS_RESOLVE_URL = "https://dns.google/resolve"
IPGEO_API_BASE = "https://freeipapi.com/api/json"
# crt.sh and RDAP are slow/flaky; give them a longer read budget (context only).
# TESTING: lowered for fast iteration (was 25 / 60 / 5).
SLOW_HTTP_TIMEOUT_SECONDS = 10
THREATINTEL_MAX_WAIT_SECONDS = 20
DETECTOR_POLL_INTERVAL_SECONDS = 3

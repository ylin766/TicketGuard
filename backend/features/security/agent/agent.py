"""Grey-zone security agent — LLM judgement layer (placeholder).

The deterministic pipeline writes its structured evidence to session state under
SECURITY_RESULT; this agent will read it from there and decide the verdict.

SECURITY_RESULT (ctx.session.state["security_result"]) is shaped like:
    {
        "status": "ok",                 # "ok" | "unavailable"
        "findings": [                   # threat verdicts (threat is True/False)
            {"name": "VirusTotal", "threat": True,
             "malicious": 12, "suspicious": 1, "harmless": 49, "total": 92, "detail": "..."},
            {"name": "SafeBrowsing", "threat": True,
             "threat_types": ["SOCIAL_ENGINEERING"], "detail": "..."},
            {"name": "URLhaus", "threat": False, "detail": "..."},
            {"name": "CheckPhish", "threat": False, "disposition": "clean", "detail": "..."},
            {"name": "MetaDefender", "threat": True,
             "detected_by": 1, "total": 21, "detail": "..."},
            {"name": "Sucuri", "threat": True,
             "blacklisted_by": ["Google Safe Browsing"], "malware": False, "detail": "..."},
            {"name": "OpenPhish", "threat": False, "detail": "..."},
            {"name": "PhishStats", "threat": False, "match_count": 0, "detail": "..."},
        ],
        "context": [                    # non-threat intelligence (threat is None)
            {"name": "Tranco", "threat": None, "rank": 180, "detail": "..."},
            {"name": "crt.sh", "threat": None,
             "certificate_count": 69, "earliest_certificate": "...", "detail": "..."},
            {"name": "Wayback", "threat": None,
             "has_snapshot": True, "closest_timestamp": "...", "detail": "..."},
            {"name": "RDAP", "threat": None, "registered_on": "...", "status": [...], "detail": "..."},
            {"name": "IPGeo", "threat": None,
             "ip": "...", "country": "...", "isp": "...", "detail": "..."},
        ],
        "flagged": True,                # any finding reported threat is True
        "detail": "...",                # human-readable one-line summary
    }

Each entry has its own fields; the only shared key is ``threat``
(True / False / None). Threat sources go in ``findings``; non-threat
intelligence (``threat is None``) goes in ``context`` and never sets ``flagged``.
"""

from google.adk.agents import SequentialAgent

from ....core.state_keys import SECURITY_RESULT  # noqa: F401 - evidence key for the agent
from .osint_subagent import osint_subagent

# The content_audit_agent acts as the main grey-zone LLM orchestrator.
# It currently delegates the investigation to the OSINT subagent.
# Future subagents (e.g. screenshot analysis, WHOIS deep-dive) can be added here.
content_audit_agent = SequentialAgent(
    name="content_audit_agent",
    sub_agents=[osint_subagent],
    description="Main security LLM agent that orchestrates subagents like OSINT to make a final grey-zone verdict based on SECURITY_RESULT.",
)

"""Grey-zone security agent — LLM judgement layer (placeholder).

The deterministic pipeline writes its structured evidence to session state under
SECURITY_RESULT; this agent will read it from there and decide the verdict.

SECURITY_RESULT (ctx.session.state["security_result"]) is shaped like:
    {
        "status": "ok",                 # "ok" | "unavailable"
        "findings": [                   # one native report per threat-intel source
            {"name": "VirusTotal",   "kind": "reputation_score",
             "malicious": 12, "suspicious": 1, "total": 92, "detail": "..."},
            {"name": "SafeBrowsing", "kind": "blacklist_verdict",
             "listed": True, "threats": ["SOCIAL_ENGINEERING"], "detail": "..."},
            {"name": "URLhaus",      "kind": "blacklist_verdict",
             "listed": False, "threats": [], "detail": "..."},
        ],
        "flagged": True,                # any source reported a threat
        "detail": "...",                # human-readable one-line summary
    }
"""

from ....core.state_keys import SECURITY_RESULT  # noqa: F401 - evidence key for the agent

# TODO: define the grey-zone LLM agent that reads SECURITY_RESULT and judges it.


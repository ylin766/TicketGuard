"""Security score synthesis — turn raw threat-intel findings into one number.

Layer 1 (the deterministic pipeline) queries up to 13 sources and returns a
``security_result`` dict of raw, per-source facts. It deliberately does NOT
synthesize a score. This module is Layer 2: it collapses that evidence into a
single ``websiteCredibility.score`` integer (0 = extremely dangerous,
100 = completely safe) that the frontend can display, plus a human-readable
breakdown for debugging.

All thresholds and weights are module-level constants so they can be tuned
without touching the logic. Every function tolerates missing / None fields:
the pipeline only includes sources that actually returned, so any field may be
absent on any given run.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger("ticketguard.scoring")

# --------------------------------------------------------------------------- #
# Tunable constants                                                           #
# --------------------------------------------------------------------------- #

# Score returned when the whole pipeline is unavailable (no source resolved):
# we genuinely cannot tell, so we sit on the fence rather than claim safe.
UNAVAILABLE_SCORE = 50

# Base penalty subtracted from 100 when a threat source reports threat=True.
THREAT_BASE_WEIGHTS: dict[str, int] = {
    "VirusTotal": 25,
    "SafeBrowsing": 25,
    "URLhaus": 15,
    "CheckPhish": 10,
    "MetaDefender": 10,
    "Sucuri": 10,
    "OpenPhish": 15,
    "PhishStats": 10,
}

# VirusTotal / MetaDefender penalties scale by detection ratio. A handful of
# engines flagging a popular URL is weak signal; multiply the ratio so that even
# a modest fraction of engines reaches the full weight.
DETECTION_RATIO_MULTIPLIER = 5.0

# Context (non-threat intelligence) penalties.
RDAP_NEW_DOMAIN_PENALTY = 20      # registered < NEW_DOMAIN_DAYS ago
RDAP_YOUNG_DOMAIN_PENALTY = 10    # registered NEW..YOUNG days ago
RDAP_UNKNOWN_AGE_PENALTY = 15     # registration date missing/unparseable
TRANCO_NO_RANK_PENALTY = 10       # domain absent from the Tranco list
TRANCO_LOW_RANK_PENALTY = 5       # ranked, but worse than LOW_RANK_THRESHOLD
WAYBACK_NO_SNAPSHOT_PENALTY = 10  # no Internet Archive history at all
FEW_CERTS_PENALTY = 5             # fewer than MIN_CERTIFICATE_COUNT CT certs
FOREIGN_HOSTING_PENALTY = 3       # hosted outside the common-hosting set

# Context can never, on its own, drop a site below 60.
CONTEXT_PENALTY_CAP = 40

# Domain-age bands (days).
NEW_DOMAIN_DAYS = 30
YOUNG_DOMAIN_DAYS = 90

# Tranco rank worse than this is treated as effectively unranked-but-present.
TRANCO_LOW_RANK_THRESHOLD = 1_000_000

# crt.sh: a domain with almost no certificate history is weakly suspicious.
MIN_CERTIFICATE_COUNT = 2

# Countries that host the overwhelming majority of legitimate ticketing sites.
COMMON_HOSTING_COUNTRIES = frozenset(
    {"US", "CA", "MX", "GB", "DE", "FR", "NL", "IE"}
)

# classify_risk band edges (upper-exclusive).
RISK_CRITICAL_MAX = 20
RISK_HIGH_MAX = 40
RISK_MEDIUM_MAX = 60
RISK_LOW_MAX = 80


# --------------------------------------------------------------------------- #
# Small helpers                                                               #
# --------------------------------------------------------------------------- #

def _clamp(value: float, low: int, high: int) -> int:
    """Clamp ``value`` into ``[low, high]`` and return it as an int.

    Args:
        value: The raw value to clamp.
        low: Inclusive lower bound.
        high: Inclusive upper bound.

    Returns:
        ``value`` rounded/truncated to an int and constrained to the bounds.
    """
    return int(max(low, min(high, value)))


def _find(entries: list[dict] | None, name: str) -> dict | None:
    """Return the first entry whose ``name`` matches, or None.

    Args:
        entries: A findings or context list (may be None or contain odd items).
        name: The source name to look for, e.g. ``"RDAP"``.

    Returns:
        The matching entry dict, or None if absent.
    """
    for entry in entries or ():
        if isinstance(entry, dict) and entry.get("name") == name:
            return entry
    return None


def compute_domain_age_days(registered_on: str | None) -> int | None:
    """Return the number of whole days since a domain was registered.

    Accepts plain ISO dates (``"2024-01-15"``) and ISO datetimes with an
    optional trailing ``Z`` (``"2024-01-15T00:00:00Z"``). Naive timestamps are
    assumed to be UTC.

    Args:
        registered_on: The registration date string, or None.

    Returns:
        Whole days since registration (never negative), or None if the input is
        missing or cannot be parsed.
    """
    if not registered_on:
        return None

    text = registered_on.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        # Fall back to the leading date portion (handles odd time suffixes).
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            logger.debug("Could not parse registration date: %r", registered_on)
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    delta = datetime.now(timezone.utc) - parsed
    return max(delta.days, 0)


# --------------------------------------------------------------------------- #
# Penalty computation                                                         #
# --------------------------------------------------------------------------- #

def _threat_penalty_for(finding: dict) -> int:
    """Compute the penalty for a single threat finding (threat=True).

    Most sources contribute their flat base weight. VirusTotal and MetaDefender
    instead scale that weight by their detection ratio, so a 1-of-92 hit costs
    far less than a 20-of-92 hit.

    Args:
        finding: One entry from ``security_result["findings"]``.

    Returns:
        The penalty for this finding (0 if it is not an active threat).
    """
    if finding.get("threat") is not True:
        return 0

    name = finding.get("name", "")
    base = THREAT_BASE_WEIGHTS.get(name, 0)
    if base == 0:
        return 0

    if name == "VirusTotal":
        return _ratio_scaled_penalty(
            base, finding.get("malicious"), finding.get("total")
        )
    if name == "MetaDefender":
        return _ratio_scaled_penalty(
            base, finding.get("detected_by"), finding.get("total")
        )
    return base


def _ratio_scaled_penalty(base: int, detected: object, total: object) -> int:
    """Scale ``base`` by ``detected / total`` (boosted and capped at 1.0).

    Used by multi-engine sources. If the counts are missing or unusable we fall
    back to the full base weight, since the source still reported a threat.

    Args:
        base: The source's base weight.
        detected: Number of engines that flagged the URL.
        total: Total number of engines consulted.

    Returns:
        The scaled penalty as an int.
    """
    try:
        detected_n = float(detected)  # type: ignore[arg-type]
        total_n = float(total)        # type: ignore[arg-type]
    except (TypeError, ValueError):
        return base

    if total_n <= 0:
        return base

    ratio = min((detected_n / total_n) * DETECTION_RATIO_MULTIPLIER, 1.0)
    return int(base * ratio)


def _context_penalty(context: list[dict] | None) -> tuple[int, list[dict]]:
    """Sum the credibility penalties from the non-threat intelligence sources.

    The returned penalty is the raw (uncapped) total; the caller applies
    ``CONTEXT_PENALTY_CAP``. A structured per-item list is returned alongside for
    the breakdown, in source order — each item is ``{"label", "points"}``.

    Args:
        context: The ``security_result["context"]`` list (may be None).

    Returns:
        A ``(raw_penalty, items)`` tuple.
    """
    penalty = 0
    items: list[dict] = []

    def add(points: int, label: str) -> None:
        nonlocal penalty
        penalty += points
        items.append({"label": label, "points": points})

    rdap = _find(context, "RDAP")
    if rdap is not None:
        registered_on = rdap.get("registered_on")
        age = compute_domain_age_days(registered_on)
        if age is None:
            add(RDAP_UNKNOWN_AGE_PENALTY, "Domain registration date could not be verified")
        elif age < NEW_DOMAIN_DAYS:
            add(RDAP_NEW_DOMAIN_PENALTY, f"Domain registered {age} days ago")
        elif age < YOUNG_DOMAIN_DAYS:
            add(RDAP_YOUNG_DOMAIN_PENALTY, f"Domain registered {age} days ago")

    tranco = _find(context, "Tranco")
    if tranco is not None:
        rank = tranco.get("rank")
        if rank is None:
            add(TRANCO_NO_RANK_PENALTY, "Not in the Tranco popularity list")
        elif isinstance(rank, (int, float)) and rank > TRANCO_LOW_RANK_THRESHOLD:
            add(TRANCO_LOW_RANK_PENALTY, f"Very low Tranco rank ({int(rank)})")

    wayback = _find(context, "Wayback")
    if wayback is not None and not wayback.get("has_snapshot"):
        add(WAYBACK_NO_SNAPSHOT_PENALTY, "No Wayback Machine history")

    crtsh = _find(context, "crt.sh")
    if crtsh is not None:
        cert_count = crtsh.get("certificate_count")
        if isinstance(cert_count, int) and cert_count < MIN_CERTIFICATE_COUNT:
            add(FEW_CERTS_PENALTY, "Almost no TLS certificate history")

    ipgeo = _find(context, "IPGeo")
    if ipgeo is not None:
        country = ipgeo.get("country")
        if country and country not in COMMON_HOSTING_COUNTRIES:
            add(FOREIGN_HOSTING_PENALTY, f"Hosted in an unusual country ({country})")

    return penalty, items


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #

def compute_security_score(security_result: dict | None) -> int:
    """Collapse a ``security_result`` into a single 0-100 credibility score.

    Args:
        security_result: The Layer 1 pipeline output. If it is empty or its
            ``status`` is ``"unavailable"``, the score is ``UNAVAILABLE_SCORE``.

    Returns:
        An integer 0-100 (100 = completely safe, 0 = extremely dangerous).
    """
    if not security_result or security_result.get("status") == "unavailable":
        return UNAVAILABLE_SCORE

    findings = security_result.get("findings") or []
    context = security_result.get("context") or []

    threat_penalty = sum(_threat_penalty_for(f) for f in findings)
    raw_context_penalty, _ = _context_penalty(context)
    context_penalty = min(raw_context_penalty, CONTEXT_PENALTY_CAP)

    score = _clamp(100 - threat_penalty - context_penalty, 0, 100)
    logger.debug(
        "score=%d (threat_penalty=%d, context_penalty=%d)",
        score, threat_penalty, context_penalty,
    )
    return score


def classify_risk(score: int) -> str:
    """Map a 0-100 score to a coarse risk band.

    Args:
        score: The credibility score from :func:`compute_security_score`.

    Returns:
        One of ``"critical"``, ``"high"``, ``"medium"``, ``"low"``, ``"safe"``.
    """
    if score < RISK_CRITICAL_MAX:
        return "critical"
    if score < RISK_HIGH_MAX:
        return "high"
    if score < RISK_MEDIUM_MAX:
        return "medium"
    if score < RISK_LOW_MAX:
        return "low"
    return "safe"


def _build_explanation(triggered: list[str], context_flags: list[str]) -> str:
    """Compose a 1-2 sentence, data-driven summary of the verdict.

    Args:
        triggered: Names of threat sources that fired.
        context_flags: Human-readable context warnings.

    Returns:
        A short natural-language explanation.
    """
    if triggered:
        count = len(triggered)
        plural = "s" if count != 1 else ""
        sentence = (
            f"{count} threat intelligence source{plural} flagged this URL "
            f"({', '.join(triggered)})."
        )
    else:
        sentence = "No threat intelligence source flagged this URL."

    if context_flags:
        sentence += " " + "; ".join(context_flags) + "."

    return sentence


def generate_score_breakdown(security_result: dict | None) -> dict:
    """Produce a full, display-friendly breakdown of how the score was reached.

    Args:
        security_result: The Layer 1 pipeline output.

    Returns:
        A dict with keys: ``score``, ``risk_level``, ``threat_penalty``,
        ``context_penalty``, ``threat_sources_triggered``, ``context_flags``,
        and ``explanation``.
    """
    if not security_result or security_result.get("status") == "unavailable":
        return {
            "score": UNAVAILABLE_SCORE,
            "risk_level": classify_risk(UNAVAILABLE_SCORE),
            "threat_penalty": 0,
            "context_penalty": 0,
            "threat_sources_triggered": [],
            "context_flags": [],
            "deductions": [],
            "explanation": (
                "Threat intelligence was unavailable, so risk could not be "
                "determined."
            ),
        }

    findings = security_result.get("findings") or []
    context = security_result.get("context") or []

    threat_penalty = sum(_threat_penalty_for(f) for f in findings)
    triggered = [
        f.get("name", "unknown")
        for f in findings
        if f.get("threat") is True
    ]
    # Per-threat-source deductions (label + the points it cost), for the UI.
    threat_items = [
        {"label": f"{f.get('name', 'A source')} flagged this URL", "points": pen}
        for f in findings
        if (pen := _threat_penalty_for(f)) > 0
    ]

    raw_context_penalty, context_items = _context_penalty(context)
    context_penalty = min(raw_context_penalty, CONTEXT_PENALTY_CAP)
    context_flags = [i["label"] for i in context_items]

    score = _clamp(100 - threat_penalty - context_penalty, 0, 100)

    return {
        "score": score,
        "risk_level": classify_risk(score),
        "threat_penalty": threat_penalty,
        "context_penalty": context_penalty,
        "threat_sources_triggered": triggered,
        "context_flags": context_flags,
        # Flat, ordered list of every point deduction (threat first, then
        # context) so the UI can list exactly what cost the site its points.
        "deductions": threat_items + context_items,
        "explanation": _build_explanation(triggered, context_flags),
    }

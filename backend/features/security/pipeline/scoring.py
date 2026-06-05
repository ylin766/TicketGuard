"""Weighted aggregation of the security detectors — deterministic, no LLM.

Combines each detector's normalized risk score with per-detector weights
(renormalized over whichever detectors actually returned a result).

Score convention: higher = more trustworthy (0-100), matching seat / price.
"""

from .constants import DETECTOR_WEIGHTS, NEUTRAL_SCORE


def aggregate(results: dict[str, dict]) -> dict:
    """Combine detector risk scores into one weighted trust score.

    Args:
        results: mapping of detector name -> its normalized result dict, e.g.
            {"intelowl": {...}, "spiderfoot": {...}}.

    Returns:
        dict with keys: score (0-100, higher = safer), flags, detail.
    """
    available = {
        name: raw
        for name, raw in results.items()
        if raw and raw.get("status") == "ok" and raw.get("risk_score") is not None
    }

    if not available:
        return {
            "score": NEUTRAL_SCORE,
            "flags": ["detectors_unavailable"],
            "detail": "No security detector returned a result.",
        }

    total_weight = sum(DETECTOR_WEIGHTS[name] for name in available)
    weighted_risk = sum(
        DETECTOR_WEIGHTS[name] * raw["risk_score"] for name, raw in available.items()
    ) / total_weight
    trust_score = round(100 - weighted_risk)

    flags: list[str] = []
    for name, raw in available.items():
        flags.extend(f"{name}:{flag}" for flag in raw.get("flags", []))

    detail = " ".join(
        f"[{name}] {raw.get('detail', '')}".strip() for name, raw in available.items()
    )
    return {"score": trust_score, "flags": flags, "detail": detail}

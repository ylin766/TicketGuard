"""Seat agent: score a section's seat-view photo across quantified dimensions.

This is the "seat agent" slot the team reserved. Given one real seat-view photo
(from the bundled library) plus the listing's price, it asks Gemini to grade the
seat against a fixed rubric and emit a strict JSON shape the frontend can render
(radar / bars + an overall ring badge).

Same conventions as price.analysis: best-effort (never raises — returns None on
any failure so price/seat enrichment can't break), temperature 0, JSON response
mode. Direct google.genai calls are auto-traced by the GenAIInstrumentor wired
in backend.observability.telemetry.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from ..price.analysis import extract_json

logger = logging.getLogger("ticketguard.seats.agent")

MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Quantified rubric. Each dimension is scored 0–100; the overall is their
# weighted sum. Weights sum to 1.0. Kept here (not in the prompt string only) so
# the backend can recompute / sanity-check the model's overall if needed.
DIMENSION_WEIGHTS: dict[str, float] = {
    "view_clarity": 0.30,   # unobstructed sightline to the pitch
    "proximity": 0.25,      # distance + angle relative to the field
    "value": 0.20,          # seat quality for the asking price
    "obstruction": 0.15,    # railings / roof / ad boards / handrails
    "atmosphere": 0.10,     # closeness to supporter sections / corner energy
}

_RUBRIC_TEXT = """\
You are a stadium seating expert grading ONE seat location for a football
(soccer) match, looking at a real fan-submitted photo taken from that section.

Grade these five dimensions, each 0-100 (higher is better):
- view_clarity (weight 0.30): how clear and open the sightline to the pitch is.
- proximity (weight 0.25): how close and well-angled the seat is to the field.
- value (weight 0.20): seat quality relative to the asking price.
- obstruction (weight 0.15): freedom from railings, roof edges, ad boards, poles.
- atmosphere (weight 0.10): proximity to supporter sections / corner energy.

Rules:
- Judge ONLY from the photo and the given price. Do not invent facts.
- overall = round(sum(dimension.score * weight)).
- ring is derived from overall: >=85 excellent, >=70 great, >=55 good,
  >=40 fair, else poor.
- confidence reflects how clearly the photo supports your grades.

Return STRICT JSON, no prose, exactly this shape:
{
  "overall": <int 0-100>,
  "ring": "excellent|great|good|fair|poor",
  "dimensions": {
    "view_clarity": {"score": <int>, "note": "<short reason>"},
    "proximity":    {"score": <int>, "note": "<short reason>"},
    "value":        {"score": <int>, "note": "<short reason>"},
    "obstruction":  {"score": <int>, "note": "<short reason>"},
    "atmosphere":   {"score": <int>, "note": "<short reason>"}
  },
  "summary": "<one sentence buyer-facing takeaway>",
  "confidence": "high|medium|low"
}
"""

_client = None  # lazily-initialized google.genai.Client


def _get_client():
    global _client
    if _client is None:
        from google import genai  # lazy: heavy + needs credentials

        _client = genai.Client()
    return _client


def _read_image(path: str) -> Optional[bytes]:
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except Exception:  # noqa: BLE001
        return None


def _ring_for(overall: int) -> str:
    if overall >= 85:
        return "excellent"
    if overall >= 70:
        return "great"
    if overall >= 55:
        return "good"
    if overall >= 40:
        return "fair"
    return "poor"


def _coerce(result: dict) -> Optional[dict]:
    """Validate / normalize the model output; return None if unusable."""
    dims = result.get("dimensions")
    if not isinstance(dims, dict):
        return None
    norm_dims: dict[str, dict] = {}
    for key in DIMENSION_WEIGHTS:
        d = dims.get(key) or {}
        try:
            score = int(round(float(d.get("score"))))
        except (TypeError, ValueError):
            score = 0
        score = max(0, min(100, score))
        note = str(d.get("note") or "")
        norm_dims[key] = {"score": score, "note": note}

    # Recompute overall from weights so it's always self-consistent.
    overall = round(
        sum(norm_dims[k]["score"] * w for k, w in DIMENSION_WEIGHTS.items())
    )
    overall = max(0, min(100, int(overall)))

    confidence = result.get("confidence")
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"

    return {
        "overall": overall,
        "ring": _ring_for(overall),
        "dimensions": norm_dims,
        "summary": str(result.get("summary") or ""),
        "confidence": confidence,
    }


def score_seat(
    section: str,
    photo_path: str,
    price: Optional[float] = None,
    view: Optional[str] = None,
) -> Optional[dict]:
    """Grade one section from its seat-view photo. Returns None on any failure.

    Args:
        section: section id (for the prompt context only).
        photo_path: local path to a representative seat-view photo.
        price: the listing's asking price, if known (informs the value score).
        view: the marketplace's view label, e.g. "Clear View", if any.
    """
    image_bytes = _read_image(photo_path)
    if not image_bytes:
        return None

    context = f"Section: {section}."
    if price is not None:
        context += f" Asking price: ${price}."
    if view:
        context += f" Marketplace view label: {view}."

    try:
        from google.genai import types

        resp = _get_client().models.generate_content(
            model=MODEL_NAME,
            contents=[
                _RUBRIC_TEXT + "\n\n" + context,
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            ],
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
            ),
        )
        parsed = extract_json(resp.text or "{}")
    except Exception as exc:  # noqa: BLE001 - scoring must never break the stream
        logger.warning("[seats] Gemini scoring failed: %s", str(exc)[:160])
        return None

    return _coerce(parsed)

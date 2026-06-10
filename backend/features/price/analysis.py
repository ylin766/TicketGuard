"""Price analysis: turn a user's listing + the live market into a structured,
frontend-ready verdict.

Two-part design:

1. **Multimodal extraction** — Gemini looks at a screenshot of the page the user
   pasted and pulls out *their* ticket (section / row / quantity / price) as a
   normalized JSON. This is site-agnostic: no per-site "selected listing" DOM
   selectors to maintain.

2. **Grounded evaluation** — the deterministic market listings (from the
   scraper) plus a few computed statistics are handed back to Gemini *as
   context* to produce a buyer-facing assessment + recommendations, emitted as a
   strict JSON shape the frontend can drop into each panel.

Everything Gemini-related is best-effort: if credentials/packages are missing or
a call fails, we fall back to deterministic stats only, so price never breaks.
Direct ``google.genai`` calls are auto-traced by the GenAIInstrumentor wired in
``backend.observability.telemetry``.
"""

from __future__ import annotations

import json
import logging
import os
from statistics import median as _median
from typing import Optional

logger = logging.getLogger("ticketguard.price.analysis")

MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

_client = None  # lazily-initialized google.genai.Client


def _get_client():
    """Return a cached ``google.genai.Client`` (created on first call)."""
    global _client
    if _client is None:
        from google import genai  # lazy: heavy + needs credentials

        _client = genai.Client()
    return _client


def extract_json(text: str) -> dict:
    """Parse a model response into a dict, tolerating markdown fences / prose."""
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        pass
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = (
            cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        )
    try:
        return json.loads(cleaned)
    except Exception:  # noqa: BLE001
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except Exception:  # noqa: BLE001
            pass
    logger.warning("could not parse Gemini JSON: %r", text[:200])
    return {}


def _gemini_json(prompt: str, image_bytes: Optional[bytes] = None) -> dict:
    """Call Gemini for a JSON object, attaching a screenshot if provided.

    Returns ``{}`` on any failure so callers can fall back to deterministic-only.
    """
    try:
        from google.genai import types

        contents: list = [prompt]
        if image_bytes:
            contents.append(
                types.Part.from_bytes(data=image_bytes, mime_type="image/png")
            )
        resp = _get_client().models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
            ),
        )
        return extract_json(resp.text or "{}")
    except Exception as exc:  # noqa: BLE001 - analysis must never break price
        logger.warning("[price] Gemini call failed: %s", str(exc)[:160])
        return {}


# ---------------------------------------------------------------------------
# 1a. Deterministic match: find the buyer's listing straight from the URL
# ---------------------------------------------------------------------------

# Query keys various sites use to deep-link a single resale listing.
_LISTING_ID_KEYS = ("listingid", "listing_id", "lid", "sellerlistingid")


def parse_listing_id(url: str) -> Optional[str]:
    """Extract a listing id from a ticket URL, if present (query or path).

    StubHub/Ticketmaster deep-links to one listing look like
    ``.../event/153022393/?listingId=12442049570&quantity=2``. Returns the id as
    a string, or None when the URL is just an event/listing page.
    """
    if not url:
        return None
    try:
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(url)
        qs = {k.lower(): v for k, v in parse_qs(parsed.query).items()}
        for key in _LISTING_ID_KEYS:
            if key in qs and qs[key]:
                return str(qs[key][0]).strip()
        # Path form: .../listing/12442049570
        import re

        m = re.search(r"/listing[s]?/(\d{5,})", parsed.path)
        if m:
            return m.group(1)
    except Exception:  # noqa: BLE001
        return None
    return None


def match_user_listing(url: str, listings: list[dict]) -> dict:
    """Deterministically match the buyer's listing from the URL's listing id.

    Returns a normalized user-listing dict (same shape as the vision output) when
    a scraped listing matches the URL's id, else ``{}``.
    """
    lid = parse_listing_id(url)
    if not lid:
        return {}
    for x in listings:
        if not isinstance(x, dict):
            continue
        if str(x.get("listing_id") or "").strip() == lid:
            price = x.get("price")
            qty = x.get("ticket_count")
            return {
                "section": x.get("section"),
                "row": x.get("row"),
                "seat": None,
                "quantity": qty if isinstance(qty, int) else None,
                "price_per_ticket": price if isinstance(price, (int, float)) else None,
                "total_price": None,
                "currency": None,
                "seller_notes": None,
                "listing_id": lid,
                "confidence": "high",
                "source": "url_match",
            }
    return {}


def _seat_key(section, row, seat=None) -> tuple:
    """Normalized identity for a seat: (section, row, seat) lower/stripped."""
    def norm(v):
        return str(v).strip().lower() if v not in (None, "") else ""

    return (norm(section), norm(row), norm(seat))


def find_same_seat(user: dict, listings: list[dict]) -> dict:
    """Find the market listing for the *exact same seat* the buyer is looking at.

    This is the cross-site bridge: the buyer may have seen the ticket on another
    website, so a listing id won't match. Instead we match by seat identity
    (section + row, and seat number when available) against our reference market.

    Returns the matching market listing dict, or ``{}`` when no confident match.
    """
    u_section = user.get("section")
    u_row = user.get("row")
    if not u_section:  # without at least a section we can't claim "same seat"
        return {}
    u_seat = user.get("seat")
    want_full = _seat_key(u_section, u_row, u_seat)
    want_sr = _seat_key(u_section, u_row)

    best: dict = {}
    for x in listings:
        if not isinstance(x, dict):
            continue
        have_section = x.get("section")
        have_row = x.get("row")
        # Exact section+row+seat match (strongest).
        if u_seat and _seat_key(have_section, have_row, x.get("seat_start")) == want_full:
            return x
        # Section+row match (strong, seat often not exposed in listings).
        if u_row and _seat_key(have_section, have_row) == want_sr:
            best = best or x
    return best


# ---------------------------------------------------------------------------
# 1b. Multimodal extraction of the user's own listing
# ---------------------------------------------------------------------------

_EXTRACT_PROMPT = """You are looking at a screenshot of a ticket resale page that a buyer is considering.
Extract ONLY the ticket the page is primarily showing/selecting for this buyer
(the highlighted or focused listing, the checkout summary, or the most prominent
card). Do NOT summarize the whole list.

Return a strict JSON object with these keys (use null when unknown):
{{
  "event_name": string|null,
  "venue": string|null,
  "date": string|null,
  "section": string|null,
  "row": string|null,
  "seat": string|null,
  "quantity": integer|null,
  "price_per_ticket": number|null,
  "total_price": number|null,
  "currency": string|null,
  "seller_notes": string|null,
  "confidence": "high"|"medium"|"low"
}}

Page URL: {url}
Numbers must be plain (e.g. 738, not "$738"). Output JSON only."""


def extract_user_listing(image_bytes: Optional[bytes], url: str) -> dict:
    """Use Gemini vision to extract the buyer's own ticket from a screenshot.

    Returns ``{}`` if no screenshot or extraction failed.
    """
    if not image_bytes:
        return {}
    data = _gemini_json(_EXTRACT_PROMPT.format(url=url), image_bytes)
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# 2. Deterministic market statistics (no LLM)
# ---------------------------------------------------------------------------

def _prices(listings: list[dict]) -> list[float]:
    return [
        float(x["price"])
        for x in listings
        if isinstance(x, dict) and isinstance(x.get("price"), (int, float))
    ]


# Currency symbols/prefixes seen on geo-localized ticket pages, longest first so
# multi-char prefixes (S$, US$, HK$) win over a bare "$".
_CURRENCY_PATTERNS = (
    ("US$", "USD"),
    ("S$", "SGD"),
    ("A$", "AUD"),
    ("CA$", "CAD"),
    ("C$", "CAD"),
    ("HK$", "HKD"),
    ("NZ$", "NZD"),
    ("R$", "BRL"),
    ("MX$", "MXN"),
    ("¥", "JPY"),
    ("円", "JPY"),
    ("£", "GBP"),
    ("€", "EUR"),
    ("₩", "KRW"),
    ("₹", "INR"),
    ("$", "USD"),  # bare dollar last
)


def detect_currency(listings: list[dict], default: str = "USD") -> str:
    """Detect the ISO currency code from the scraped listings' raw price text.

    Ticket sites localize prices by geography (e.g. StubHub may render SGD/JPY),
    so the currency must be read from the page, not assumed to be USD.
    """
    blob = " ".join(
        str(x.get("raw") or "")
        for x in listings
        if isinstance(x, dict)
    )
    if not blob:
        return default
    for symbol, code in _CURRENCY_PATTERNS:
        if symbol in blob:
            return code
    return default



def _norm(v) -> str:
    return str(v).strip().lower() if v is not None else ""


def compute_market_stats(
    listings: list[dict],
    user_price: Optional[float],
    user_section: Optional[str],
) -> dict:
    """Compute median / percentile / same-section figures around the user price."""
    prices = sorted(_prices(listings))
    stats: dict = {
        "count": len(prices),
        "median": float(_median(prices)) if prices else None,
        "min": prices[0] if prices else None,
        "max": prices[-1] if prices else None,
        "percentile": None,
        "same_section_median": None,
        "same_section_count": 0,
        "fair_price_range": None,
    }
    if prices:
        # Fair range = interquartile-ish band (P25–P75).
        def _pct(p: float) -> float:
            idx = min(len(prices) - 1, max(0, int(round(p * (len(prices) - 1)))))
            return prices[idx]

        stats["fair_price_range"] = {"low": _pct(0.25), "high": _pct(0.75)}

    if prices and isinstance(user_price, (int, float)):
        below = sum(1 for p in prices if p <= user_price)
        stats["percentile"] = round(100 * below / len(prices))

    if user_section:
        sec = _norm(user_section)
        same = _prices(
            [x for x in listings if _norm(x.get("section")) == sec]
        )
        stats["same_section_count"] = len(same)
        if same:
            stats["same_section_median"] = float(_median(same))
    return stats


def recommend_cheaper(
    listings: list[dict],
    user_price: Optional[float],
    user_section: Optional[str],
    limit: int = 5,
) -> list[dict]:
    """Pick better-value listings: cheaper than the user, same/any section."""
    cand = [x for x in listings if isinstance(x.get("price"), (int, float))]
    if isinstance(user_price, (int, float)):
        cand = [x for x in cand if x["price"] < user_price]
    # Prefer same section, then lowest price.
    sec = _norm(user_section)
    cand.sort(
        key=lambda x: (0 if _norm(x.get("section")) == sec else 1, x["price"])
    )
    out = []
    for x in cand[:limit]:
        out.append(
            {
                "price": x.get("price"),
                "section": x.get("section"),
                "row": x.get("row"),
                "listing_id": x.get("listing_id"),
                "badges": x.get("badges", []),
            }
        )
    return out


# ---------------------------------------------------------------------------
# 3. Grounded evaluation (Gemini, market data as context)
# ---------------------------------------------------------------------------

_EVAL_PROMPT = """You are a ticket-buying advisor. Assess whether the buyer's ticket is fairly
priced versus the live market, and give concise, actionable advice.

BUYER'S TICKET (JSON):
{user}

MARKET STATISTICS (JSON):
{stats}

A FEW BETTER-VALUE LISTINGS ALREADY FOUND (JSON):
{recs}

Return a strict JSON object:
{{
  "verdict": "good_deal"|"fair"|"slightly_high"|"overpriced"|"unknown",
  "headline": string,                     // one short sentence, buyer-facing
  "assessment": string,                   // 1-2 sentences explaining the verdict
  "savings_hint": string|null,            // e.g. "Comparable seats sell for ~X"
  "tips": [string, ...]                   // 1-3 short, practical tips
}}
All money is in the currency given by stats.currency; quote amounts with that
currency code, never assume US dollars. Base every claim on the data above.
Output JSON only."""


def evaluate(user: dict, stats: dict, recs: list[dict]) -> dict:
    """Ask Gemini for a buyer-facing verdict grounded in the market stats."""
    data = _gemini_json(
        _EVAL_PROMPT.format(
            user=json.dumps(user, ensure_ascii=False),
            stats=json.dumps(stats, ensure_ascii=False),
            recs=json.dumps(recs[:5], ensure_ascii=False),
        )
    )
    return data if isinstance(data, dict) else {}


def _fallback_verdict(stats: dict, user_price: Optional[float]) -> dict:
    """Deterministic verdict when Gemini is unavailable."""
    pct = stats.get("percentile")
    if pct is None or not isinstance(user_price, (int, float)):
        return {
            "verdict": "unknown",
            "headline": "Not enough data to grade this price.",
            "assessment": "Could not match the buyer's ticket to the live market.",
            "savings_hint": None,
            "tips": [],
        }
    if pct <= 35:
        verdict, head = "good_deal", "This looks like a good deal."
    elif pct <= 60:
        verdict, head = "fair", "This price is about average for the event."
    elif pct <= 80:
        verdict, head = "slightly_high", "This is a bit above the typical price."
    else:
        verdict, head = "overpriced", "This is priced well above the market."
    return {
        "verdict": verdict,
        "headline": head,
        "assessment": f"The price sits at the {pct}th percentile of {stats.get('count')} live listings.",
        "savings_hint": (
            f"Median is {stats.get('median'):.0f} {stats.get('currency', '')}.".strip()
            if stats.get("median")
            else None
        ),
        "tips": [],
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def analyze(
    image_bytes: Optional[bytes],
    url: str,
    listings: list[dict],
    qty: int = 2,
) -> dict:
    """Full pipeline: extract user's ticket, compute stats, evaluate, recommend.

    Returns a frontend-ready dict:
        {
          "user_listing": {...},        # url-match (preferred) or vision (may be {})
          "same_seat": {...},           # the SAME seat on our reference market (may be {})
          "stats": {...},               # deterministic market figures
          "analysis": {...},            # buyer-facing verdict (Gemini or fallback)
          "recommendations": [...],     # better-value listings
        }
    """
    # Prefer a deterministic URL match (exact, free); fall back to vision.
    user = match_user_listing(url, listings)
    if not user:
        user = extract_user_listing(image_bytes, url)
    # Override quantity with the caller's explicit choice when the user picked one.
    if qty and not user.get("quantity"):
        user["quantity"] = qty

    # Cross-site bridge: locate the *exact same seat* on our reference market, so
    # a ticket the buyer saw on another site can be compared apples-to-apples.
    same_seat = find_same_seat(user, listings)
    # If the buyer's own price is unknown but we matched their seat, use the
    # market price for that seat as the comparison anchor.
    user_price = user.get("price_per_ticket")
    if not isinstance(user_price, (int, float)):
        user_price = None
    if user_price is None and same_seat.get("price") not in (None, ""):
        sp = same_seat.get("price")
        if isinstance(sp, (int, float)):
            user_price = sp
    user_section = user.get("section")

    stats = compute_market_stats(listings, user_price, user_section)
    # Currency is geo-localized on the page; detect it so the UI formats right.
    currency = detect_currency(listings)
    stats["currency"] = currency
    if not user.get("currency"):
        user["currency"] = currency
    recs = recommend_cheaper(listings, user_price, user_section)
    analysis = evaluate(user, stats, recs) or _fallback_verdict(stats, user_price)
    # Guarantee the fallback shape even if Gemini returned a partial object.
    if "verdict" not in analysis:
        analysis = _fallback_verdict(stats, user_price)

    return {
        "user_listing": user,
        "same_seat": same_seat,
        "stats": stats,
        "analysis": analysis,
        "recommendations": recs,
    }

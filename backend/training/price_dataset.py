"""Price training dataset: turn cached market-scrape files into buyer scenarios.

Price has no ground truth, so we don't need labels — we need *scenarios*: a
buyer's ticket (event, section, price) plus the live market for that event, fed
through the analysis agent to produce a verdict that the LLM judge then scores.

Design (the 5x3 matrix the team wants):
  * Each ``(site, event)`` is scraped ONCE, offline, into a cache file under
    ``data/price_cache/<name>.json`` (same shape as ``stubhub_seats.json``:
    ``{"metadata": {...}, "tickets": [{"section","price",...}, ...]}``).
  * From each event we derive HIGH / MID / LOW buyer scenarios by picking real
    listings at the ~85th / ~50th / ~15th price percentiles — three meaningfully
    different "should I buy this?" cases per event.
  * The matrix size = (number of cache files) x 3 tiers. Drop more cache files
    (more sites/events) and the dataset grows automatically — no code change.

This keeps training offline and reproducible: the market is the cached scrape,
not a live fetch. Live scraping is a separate, occasional data-collection step.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).parent / "data" / "price_cache"

# Price percentiles used to pick the three buyer tiers from real listings.
TIER_PERCENTILES = {"low": 0.15, "mid": 0.50, "high": 0.85}


@dataclass
class PriceScenario:
    """One buyer scenario: their ticket + the event's cached market listings."""

    scenario_id: str          # e.g. "stubhub_worldcup_match14::high"
    event_url: str
    tier: str                 # "low" | "mid" | "high"
    buyer: dict               # {section, price_per_ticket, currency, ...}
    listings: list[dict]      # the event's market listings (section/price)
    metadata: dict = field(default_factory=dict)


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, round(q * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def _pick_tier_listing(listings: list[dict], q: float) -> dict | None:
    """Pick the real listing whose price is closest to the q-th percentile."""
    priced = [x for x in listings if isinstance(x.get("price"), (int, float))]
    if not priced:
        return None
    prices = sorted(float(x["price"]) for x in priced)
    target = _percentile(prices, q)
    return min(priced, key=lambda x: abs(float(x["price"]) - target))


def scenarios_from_cache_file(path: Path) -> list[PriceScenario]:
    """Build the high/mid/low buyer scenarios for one cached event file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    meta = data.get("metadata", {})
    listings = data.get("tickets") or data.get("listings") or []
    event_url = meta.get("event_url", path.stem)
    currency = meta.get("currency")
    name = path.stem

    scenarios: list[PriceScenario] = []
    for tier, q in TIER_PERCENTILES.items():
        pick = _pick_tier_listing(listings, q)
        if pick is None:
            continue
        buyer = {
            "event_name": meta.get("event_name"),
            "venue": meta.get("venue"),
            "date": meta.get("date"),
            "section": pick.get("section"),
            "price_per_ticket": pick.get("price"),
            "currency": currency,
        }
        scenarios.append(PriceScenario(
            scenario_id=f"{name}::{tier}",
            event_url=event_url,
            tier=tier,
            buyer=buyer,
            listings=listings,
            metadata=meta,
        ))
    return scenarios


def load_price_scenarios(cache_dir: Path | None = None) -> list[PriceScenario]:
    """Load every ``*_seats.json`` / ``*.json`` cache file into scenarios.

    Returns all (event x tier) scenarios across the cache dir. Empty when no
    cache files are present (the infra simply waits for scrapes)."""
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    if not cache_dir.exists():
        logger.info("[price-data] no cache dir at %s yet", cache_dir)
        return []
    scenarios: list[PriceScenario] = []
    for path in sorted(cache_dir.glob("*.json")):
        try:
            scenarios.extend(scenarios_from_cache_file(path))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[price-data] skipping %s: %s", path.name, exc)
    logger.info("[price-data] loaded %d scenarios from %s", len(scenarios), cache_dir)
    return scenarios


def build_providers(scenarios: list[PriceScenario]):
    """Build the ``(snapshot_provider, buyer_provider)`` pair the price AuditFn
    needs, keyed by scenario_id (used as the example "url").

    The snapshot provider returns ``(None, listings)`` — no screenshot, since the
    buyer ticket is injected directly; the buyer provider returns the scenario's
    buyer dict so each tier is a distinct case over the same market."""
    by_id = {s.scenario_id: s for s in scenarios}

    def snapshot_provider(key: str):
        s = by_id.get(key)
        return (None, s.listings if s else [])

    def buyer_provider(key: str):
        s = by_id.get(key)
        return dict(s.buyer) if s else {}

    return snapshot_provider, buyer_provider

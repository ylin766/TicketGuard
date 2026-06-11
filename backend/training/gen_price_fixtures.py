"""Generate diverse, realistic ticket market snapshots for price training.

We cannot live-scrape ticketing sites here (StubHub / Ticketmaster / VividSeats
load listings via JS from internal APIs behind anti-bot), so this builds a
*diverse* set of realistic market snapshots — many sites, events, venues,
currencies and price ranges — as cache files the price dataset reads. Each file
mirrors the real ``stubhub_seats.json`` shape (``metadata`` + ``tickets``), so
``price_dataset`` turns each into low/mid/high buyer scenarios automatically.

These are constructed-but-realistic fixtures (real venues/events, plausible
price distributions), explicitly NOT live scrapes — their purpose is to give
GEPA a diverse optimization signal across events, not to be a price oracle. Drop
real scraper output into the same dir to mix in genuine data.

Run:  python -m backend.training.gen_price_fixtures
"""

from __future__ import annotations

import json
import random
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "data" / "price_cache"

# Diverse FIFA World Cup 2026 matches across the three host nations (USA/Canada/
# Mexico → USD/CAD/MXN), multiple resale sites, venues, and price tiers. Stays
# strictly on-topic (World Cup) while still exercising many events/currencies.
# (event_key, site, event_name, venue, city, currency, base_price, spread, sections)
EVENTS = [
    ("sh_wc_match23", "stubhub", "Argentina vs Mexico - World Cup Group C", "SoFi Stadium", "Los Angeles", "USD", 950, 0.6, ["101", "115", "230", "318", "VIP"]),
    ("tm_wc_final", "ticketmaster", "FIFA World Cup 2026 Final", "MetLife Stadium", "New Jersey", "USD", 2800, 0.7, ["Lower 110", "Club 220", "Upper 330", "Suite"]),
    ("vs_wc_semi", "vividseats", "World Cup Semi-Final", "AT&T Stadium", "Dallas", "USD", 1600, 0.65, ["C101", "C134", "M210", "U345"]),
    ("sh_wc_match31", "stubhub", "Brazil vs Germany - World Cup R16", "Arrowhead Stadium", "Kansas City", "USD", 780, 0.7, ["105", "127", "232", "340"]),
    ("tm_wc_toronto", "ticketmaster", "Canada vs Belgium - World Cup Group B", "BMO Field", "Toronto", "CAD", 540, 0.7, ["101", "118", "210", "GA North"]),
    ("vs_wc_vancouver", "vividseats", "Croatia vs Morocco - World Cup Group F", "BC Place", "Vancouver", "CAD", 480, 0.65, ["Lower 213", "Club 240", "Upper 410"]),
    ("sh_wc_mexico", "stubhub", "Mexico vs Poland - World Cup Group A", "Estadio Azteca", "Mexico City", "MXN", 9800, 0.75, ["Cabecera Sur", "Preferente", "Palco", "General Sol"]),
    ("tm_wc_guadalajara", "ticketmaster", "Uruguay vs South Korea - World Cup Group H", "Estadio Akron", "Guadalajara", "MXN", 7200, 0.7, ["Platea Baja", "Platea Alta", "Cabecera"]),
    ("sg_wc_miami", "seatgeek", "Spain vs Japan - World Cup Group E", "Hard Rock Stadium", "Miami", "USD", 1100, 0.7, ["120", "144", "240", "340", "Club"]),
    ("gt_wc_seattle", "gametime", "England vs Netherlands - World Cup R16", "Lumen Field", "Seattle", "USD", 990, 0.65, ["100", "120", "300", "GA"]),
    ("sh_wc_houston", "stubhub", "France vs Portugal - World Cup Quarter-Final", "NRG Stadium", "Houston", "USD", 1850, 0.7, ["108", "134", "330", "Suite"]),
    ("vs_wc_atlanta", "vividseats", "USA vs Italy - World Cup Group D", "Mercedes-Benz Stadium", "Atlanta", "USD", 1250, 0.7, ["108", "126", "212", "330"]),
    ("tm_wc_monterrey", "ticketmaster", "Argentina vs Nigeria - World Cup Group C", "Estadio BBVA", "Monterrey", "MXN", 8600, 0.7, ["Platea", "Cabecera Norte", "General"]),
    ("sg_wc_boston", "seatgeek", "Netherlands vs Senegal - World Cup Group F", "Gillette Stadium", "Foxborough", "USD", 870, 0.65, ["101", "133", "211", "320"]),
    ("gt_wc_philly", "gametime", "Germany vs Colombia - World Cup Group G", "Lincoln Financial Field", "Philadelphia", "USD", 920, 0.7, ["110", "135", "215", "GA"]),
]


def _gen_listings(base: float, spread: float, sections: list[str], rng: random.Random) -> list[dict]:
    """Produce a realistic spread of listings: each section gets several seats
    with prices scattered around a section-level anchor derived from base."""
    listings: list[dict] = []
    for i, sec in enumerate(sections):
        # Better sections (earlier in list) anchor higher.
        anchor = base * (1.0 + spread * (len(sections) - i) / len(sections))
        n = rng.randint(4, 9)
        for _ in range(n):
            price = round(anchor * rng.uniform(0.8, 1.25))
            listings.append({
                "source": "fixture",
                "section": sec,
                "row": rng.choice([None, rng.randint(1, 40)]),
                "price": price,
                "view": rng.choice(["Clear View", "Side View", "Clear View", "Obstructed"]),
            })
    rng.shuffle(listings)
    return listings


def generate(out_dir: Path = CACHE_DIR, seed: int = 7) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for key, site, name, venue, city, currency, base, spread, sections in EVENTS:
        rng = random.Random(f"{seed}-{key}")
        listings = _gen_listings(base, spread, sections, rng)
        data = {
            "metadata": {
                "source": site,
                "event_url": f"https://www.{site}.com/event/{key}",
                "event_name": name,
                "venue": venue,
                "city": city,
                "currency": currency,
                "fixture": True,  # explicitly marks constructed (non-scraped) data
            },
            "tickets": listings,
        }
        path = out_dir / f"{key}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":  # pragma: no cover
    paths = generate()
    print(f"wrote {len(paths)} event fixtures -> {CACHE_DIR}")
    for p in paths:
        print("  ", p.name)

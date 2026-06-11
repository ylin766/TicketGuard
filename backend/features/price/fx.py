"""Free real-time currency conversion for World Cup price comparison.

The 2026 World Cup spans the USA, Canada and Mexico, so listings come in USD /
CAD / MXN. To compare a buyer's ticket against a market quoted in another host
currency, we normalize to a common currency using a free, keyless exchange-rate
API (open.er-api.com).

Best-effort and cached: rates are fetched once per base currency per process and
reused; on any failure we fall back to a 1:1 rate and log, so price analysis is
never blocked by the network.
"""

from __future__ import annotations

import json
import logging
import urllib.request

logger = logging.getLogger(__name__)

# Free, no-API-key endpoint. Returns {"rates": {"CAD": 1.36, "MXN": 17.1, ...}}.
_ENDPOINT = "https://open.er-api.com/v6/latest/{base}"
_TIMEOUT = 8

# Process-level cache: base currency -> {quote: rate}.
_rates_cache: dict[str, dict[str, float]] = {}


def _fetch_rates(base: str) -> dict[str, float]:
    if base in _rates_cache:
        return _rates_cache[base]
    try:
        req = urllib.request.Request(
            _ENDPOINT.format(base=base.upper()),
            headers={"User-Agent": "TicketGuard/1.0"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.load(resp)
        rates = data.get("rates") or {}
        if rates:
            _rates_cache[base] = rates
            return rates
    except Exception as exc:  # noqa: BLE001 - conversion is best-effort
        logger.warning("[fx] rate fetch failed for %s: %s", base, str(exc)[:120])
    _rates_cache[base] = {}
    return {}


def convert(amount: float, from_currency: str, to_currency: str) -> float | None:
    """Convert ``amount`` from one currency to another using live rates.

    Returns the converted amount, or ``None`` when a rate is unavailable (caller
    should then keep the original currency rather than fabricate a number)."""
    if not from_currency or not to_currency:
        return None
    if from_currency.upper() == to_currency.upper():
        return amount
    rates = _fetch_rates(from_currency)
    rate = rates.get(to_currency.upper())
    if rate is None:
        return None
    return amount * rate


def normalize_listings_currency(
    listings: list[dict], target: str, source_currency: str
) -> list[dict]:
    """Return listings with prices converted to ``target`` currency.

    Only used when comparing across host-country currencies; same-currency
    listings pass through untouched. Listings whose price can't be converted are
    left as-is (the analysis will note the currency mismatch rather than guess).
    """
    if not target or source_currency.upper() == target.upper():
        return listings
    out: list[dict] = []
    for x in listings:
        price = x.get("price")
        if isinstance(price, (int, float)):
            conv = convert(float(price), source_currency, target)
            if conv is not None:
                x = {**x, "price": round(conv, 2), "original_price": price,
                     "original_currency": source_currency}
        out.append(x)
    return out

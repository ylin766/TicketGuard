"""Price feature: live ticket-price collection across resale marketplaces.

Public API:
    fetch_stubhub(url, qty, on_frame=None)       -> dict   (stubhub.py)
    fetch_ticketmaster(url, qty, on_frame=None)  -> dict   (ticketmaster.py)
    compute_median(listings)                     -> float | None  (service.py)
    stream_price(url, qty)                        -> AsyncGenerator (service.py)

The scrapers run a HEADED browser (headless=False) because resale sites degrade
accuracy / block headless. The optional ``on_frame`` callback receives a PNG
screenshot per step so the frontend can show a live "clay viewport" instead of a
raw OS window.
"""

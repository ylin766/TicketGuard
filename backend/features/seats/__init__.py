"""Seats feature: map price-scraper listings to seat-view photos.

Pure, local, LLM-free enrichment. Given the price scraper's ``metadata.venue``
and each listing's ``section``, glob the bundled seat-photo library and attach
public photo URLs + a match status to every listing.

Public API:
    match_seats(venue, listings, image_base_url=None) -> list[dict]  (service.py)
    SEATS_DATA_DIR                                                   (service.py)
"""

from .service import (
    match_seats,
    attach_seat_photos,
    select_scoring_order,
    SEATS_DATA_DIR,
)

__all__ = [
    "match_seats",
    "attach_seat_photos",
    "select_scoring_order",
    "SEATS_DATA_DIR",
]

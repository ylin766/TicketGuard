"""Seats matching service: enrich price listings with seat-view photos.

This is a pure, in-memory port of ``backend/seats/match_tickets.py`` — same
venue/section matching logic, but it takes the price scraper's data structures
directly (no JSON file, no argparse) and returns enriched listing dicts instead
of writing a CSV. No LLM, no network: just venue folder resolution + glob.
"""

from __future__ import annotations

import difflib
import glob
import os
import re
from urllib.parse import quote

# The bundled seat-photo library lives under backend/seats/seats-data.
# backend/features/seats/service.py -> backend/seats/seats-data
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SEATS_DATA_DIR = os.path.abspath(
    os.path.join(_THIS_DIR, "..", "..", "seats", "seats-data")
)
DEFAULT_PHOTOS_ROOT = os.path.join(SEATS_DATA_DIR, "photos_avfms")

# Public base URL the frontend uses to fetch photos. The FastAPI app mounts
# SEATS_DATA_DIR at this path, so URLs look like
# {base}/photos_avfms/<venue>/section217-1.jpg
DEFAULT_IMAGE_BASE_URL = os.environ.get(
    "SEAT_IMAGE_BASE_URL", "/seat-photos"
)


def _norm_venue(s: str) -> str:
    s = (s or "").lower().replace("&", "")
    s = re.sub(r"\band\b", "", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    for suf in ("stadium", "field", "place", "arena", "park"):
        if s.endswith(suf) and len(s) > len(suf) + 2:
            s = s[: -len(suf)]
    return s


def _resolve_folder(venue: str, candidates: list[str]) -> str | None:
    """Pick the candidate dir whose normalized name best matches the venue."""
    nv = _norm_venue(venue)
    nmap = {_norm_venue(c): c for c in candidates}
    if nv in nmap:
        return nmap[nv]
    hit = difflib.get_close_matches(nv, list(nmap.keys()), n=1, cutoff=0.55)
    return nmap[hit[0]] if hit else None


def _classify(section, stype) -> tuple[str, str | None, str | None]:
    s = str(section).strip()
    if stype == "category" or s.lower().startswith("category"):
        return "category", None, None
    if stype == "supporters" or "support" in s.lower():
        return "supporters", None, None
    if stype is None and not re.search(r"\d", s):
        return "unmatchable", None, None
    m = re.fullmatch(r"([A-Za-z]{0,3})(\d{1,4})([A-Za-z]{0,2})", s)
    if m:
        return "section", s, m.group(2)  # full id, base number
    return "unmatchable", None, None


def _find_photos(folder: str, full: str | None, base: str | None):
    for key, tag in ((full, "matched"), (base, "matched_base")):
        if not key:
            continue
        hits: list[str] = []
        for ext in ("jpg", "jpeg", "png", "webp"):
            hits += glob.glob(os.path.join(folder, f"section{key}-*.{ext}"))
            hits += glob.glob(os.path.join(folder, f"section{key}.{ext}"))
        if hits:
            return sorted(hits), tag
    return [], None


def _build_photo_url(photo_path: str, photos_root: str, image_base_url: str) -> str:
    """Build the public URL served from the seats-data directory."""
    source_name = os.path.basename(os.path.normpath(photos_root))
    relative_path = os.path.relpath(photo_path, photos_root)
    url_parts = [source_name, *relative_path.split(os.sep)]
    encoded_path = "/".join(quote(part, safe="") for part in url_parts)
    return f"{image_base_url.rstrip('/')}/{encoded_path}"


def match_seats(
    venue: str,
    listings: list[dict],
    image_base_url: str | None = None,
    photos_root: str | None = None,
    with_agent_score: bool = False,
    score_top_n: int = 6,
) -> list[dict]:
    """Attach seat-view photos to each listing in-place and return the list.

    Args:
        venue: ``metadata.venue`` from the price scraper, e.g. "Mercedes-Benz Stadium".
        listings: price scraper listings; each needs ``section`` and ``section_type``.
        image_base_url: public base for photo URLs (default ``/seat-photos``).
        photos_root: override the photo library root (default bundled photos_avfms).
        with_agent_score: when True, run the seat agent (Gemini) on up to
            ``score_top_n`` matched listings and attach ``seat_score``.
        score_top_n: max number of matched listings to grade (cheapest first),
            to bound token cost and latency.

    Each listing gets these added keys:
        match_status: matched | matched_base | no_photo | category |
                      supporters | unmatchable
        photo_count:  number of photos found
        photo_urls:   list[str] of public URLs (empty when none)
        seat_score:   dict|None — present only when graded (see seats.agent)
    """
    base_url = image_base_url or DEFAULT_IMAGE_BASE_URL
    root = os.path.abspath(photos_root or DEFAULT_PHOTOS_ROOT)

    local_first_photo = attach_seat_photos(
        venue, listings, image_base_url=base_url, photos_root=root
    )

    if with_agent_score and local_first_photo:
        _score_listings(listings, local_first_photo, score_top_n)

    return listings


def attach_seat_photos(
    venue: str,
    listings: list[dict],
    image_base_url: str | None = None,
    photos_root: str | None = None,
) -> dict[int, str]:
    """Photo matching only (no LLM). Mutates each listing with match_status /
    photo_count / photo_urls and returns ``{listing_index: local_photo_path}``
    for the listings that matched a real photo (so a caller can grade them).
    """
    base_url = image_base_url or DEFAULT_IMAGE_BASE_URL
    root = os.path.abspath(photos_root or DEFAULT_PHOTOS_ROOT)

    folder = None
    if os.path.isdir(root):
        subdirs = [
            d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))
        ]
        vfolder = _resolve_folder(venue, subdirs)
        folder = os.path.join(root, vfolder) if vfolder else None

    # Remember the first local photo path per listing so the seat agent can read
    # the actual image bytes (photo_urls are public URLs, not local paths).
    local_first_photo: dict[int, str] = {}

    for idx, t in enumerate(listings):
        kind, full, base = _classify(t.get("section"), t.get("section_type"))
        photos: list[str] = []
        tag = None
        status = kind if kind != "section" else "no_photo"
        if kind == "section" and folder:
            photos, tag = _find_photos(folder, full, base)
            if tag:
                status = tag
        t["match_status"] = status
        t["photo_count"] = len(photos)
        t["photo_urls"] = [
            _build_photo_url(p, root, base_url) for p in photos
        ]
        t.setdefault("seat_score", None)
        if photos:
            local_first_photo[idx] = photos[0]

    return local_first_photo


def select_scoring_order(
    listings: list[dict],
    local_first_photo: dict[int, str],
    top_n: int,
    prioritize_section: str | None = None,
) -> list[int]:
    """Pick which matched listings to grade, capped at ``top_n``.

    Goal: let the buyer see where THEIR seat stands. So we always grade the
    buyer's own section, then sample a comparison set spread around the buyer's
    price — roughly half cheaper, half pricier — so the report shows some seats
    better and some worse than theirs. Without a known buyer section we fall
    back to a price spread across the whole market (cheapest → priciest).
    """

    def _price(idx: int) -> float:
        p = listings[idx].get("price")
        return float(p) if isinstance(p, (int, float)) else float("inf")

    ordered = sorted(local_first_photo.keys(), key=_price)
    if not ordered:
        return []

    target = _section_base(prioritize_section)
    yours = (
        [i for i in ordered if _section_base(str(listings[i].get("section") or "")) == target]
        if target is not None
        else []
    )

    if not yours:
        # No buyer section to anchor on — sample an even price spread so the
        # grades still span cheap → expensive instead of only the cheapest.
        return _even_spread(ordered, top_n)

    anchor = yours[0]
    anchor_price = _price(anchor)
    rest = [i for i in ordered if i not in yours]
    cheaper = [i for i in rest if _price(i) < anchor_price]
    pricier = [i for i in rest if _price(i) >= anchor_price]

    # Buyer's seat first, then alternate pricier/cheaper picks spread across
    # each side so the comparison set brackets the buyer's seat.
    remaining = max(top_n - 1, 0)
    n_pricier = remaining // 2
    n_cheaper = remaining - n_pricier
    picked_pricier = _even_spread(pricier, n_pricier)
    # cheaper sorted ascending; take from the expensive end (closest to anchor)
    picked_cheaper = _even_spread(list(reversed(cheaper)), n_cheaper)

    chosen = [anchor, *picked_pricier, *picked_cheaper]
    # Top up from anything left if one side was short.
    if len(chosen) < top_n:
        for i in ordered:
            if i not in chosen:
                chosen.append(i)
            if len(chosen) >= top_n:
                break
    return chosen[:top_n]


def _even_spread(indices: list[int], n: int) -> list[int]:
    """Pick ``n`` items evenly spread across ``indices`` (keeps order)."""
    if n <= 0 or not indices:
        return []
    if n >= len(indices):
        return list(indices)
    step = (len(indices) - 1) / (n - 1) if n > 1 else 0
    return [indices[round(step * k)] for k in range(n)]


def _section_base(section: str | None) -> str | None:
    """Base section number (strip letter prefix/suffix) for comparison."""
    if not section:
        return None
    m = re.search(r"(\d{1,4})", str(section))
    return m.group(1) if m else None


def _score_listings(
    listings: list[dict],
    local_first_photo: dict[int, str],
    top_n: int,
) -> None:
    """Run the seat agent on up to ``top_n`` matched listings (cheapest first)."""
    from .agent import score_seat

    for idx in select_scoring_order(listings, local_first_photo, top_n):
        t = listings[idx]
        t["seat_score"] = score_seat(
            section=str(t.get("section") or ""),
            photo_path=local_first_photo[idx],
            price=t.get("price") if isinstance(t.get("price"), (int, float)) else None,
            view=t.get("view"),
        )



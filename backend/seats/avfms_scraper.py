#!/usr/bin/env python3
"""
A View From My Seat - gallery downloader.

WHAT IT DOES
  You paste one or more gallery URLs (the page that lists seat-view photos, e.g.
  a venue's "soccer" filter). For each one it:
    1. opens the page in a real Chrome window (Playwright) and dismisses the
       "disable your ad blocker" popup,
    2. reads the LAST page number and walks every page (...?page=2&, 3, ...),
    3. downloads every photo (800px /wallpaper/, falling back to /medium/),
    4. saves section / row / seat (+ member, rating) for each.

JUST EDIT THE LIST BELOW (VENUE_URLS) AND RUN.

Setup:
    pip install playwright beautifulsoup4
    playwright install chromium      # or it uses your installed Chrome

Run:
    python avfms_scraper.py

Output:
    manifest_avfms.json
    photos_avfms/<venue>/<section>__<filename>.jpg
"""

import base64
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import unquote, urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# =================== PASTE YOUR GALLERY URLS HERE ===================
VENUE_URLS = [
    "https://aviewfrommyseat.com/venue/MetLife+Stadium/seating/soccer/",
    "https://aviewfrommyseat.com/venue/BC+Place/seating/soccer/",
    "https://aviewfrommyseat.com/venue/Lumen+Field/seating/soccer/",
    "https://aviewfrommyseat.com/venue/Levi%27s+Stadium/seating/soccer/",
    "https://aviewfrommyseat.com/venue/SoFi+Stadium/seating/soccer/",
    "https://aviewfrommyseat.com/venue/Arrowhead+Stadium/seating/soccer/",
    "https://aviewfrommyseat.com/venue/AT-and-T+Stadium/seating/soccer/",
    "https://aviewfrommyseat.com/venue/NRG+Stadium/seating/soccer/",
    "https://aviewfrommyseat.com/venue/Estadio+BBVA/seating/soccer/",
    "https://aviewfrommyseat.com/venue/Estadio+Banorte/seating/soccer/",
    "https://aviewfrommyseat.com/venue/Estadio+Akron/seating/soccer/",
    "https://aviewfrommyseat.com/venue/BMO+Field/seating/soccer/",
    "https://aviewfrommyseat.com/venue/Gillette+Stadium/seating/soccer/",
    "https://aviewfrommyseat.com/venue/MetLife+Stadium/seating/soccer/",
    "https://aviewfrommyseat.com/venue/Lincoln+Financial+Field/seating/soccer/",
    "https://aviewfrommyseat.com/venue/Mercedes-Benz+Stadium/seating/soccer/",
    "https://aviewfrommyseat.com/venue/Hard+Rock+Stadium/seating/soccer/",

    # "https://aviewfrommyseat.com/venue/BMO+Field/seating/soccer/",
]
# ====================================================================

OUT_MANIFEST = "manifest_avfms.json"
PHOTO_ROOT = "photos_avfms-1"

BROWSER_CHANNEL = "chrome"   # use installed Chrome; "" for bundled chromium
HEADLESS = False             # keep False so you can watch + look human
WAIT_AFTER_LOAD = 4000       # ms after each page load (let the popup appear)
REQUEST_DELAY = 1.0          # extra seconds between pages (be polite)
MAX_PAGES = 200              # safety cap on pagination per gallery
MAX_PHOTOS = None            # None = all; set e.g. 10 per gallery for a test
DOWNLOAD_IMAGES = True       # False = manifest only, no image files
RESUME = True                # skip images already saved (reruns don't dup)

BASE = "https://aviewfrommyseat.com"
PHOTO_HREF = re.compile(
    r"/photo/(\d+)/([^/]+)/section-([^/]+)/row-([^/]+)/seat-([^/]+)/?", re.I
)
RATING_SVG = re.compile(r"/rating_(\d)_(\d)\.svg")
THUMB_SRC = re.compile(r"/(medium|wallpaper|photos|thumbnail)/", re.I)
PAGE_NUM = re.compile(r"[?&]page=(\d+)")
GALLERY_BASE = re.compile(r"(.*/venue/[^/]+/seating/[^/?#]+)", re.I)
VENUE_SLUG = re.compile(r"/venue/([^/?#]+)/seating", re.I)


def now():
    return datetime.now(timezone.utc).isoformat()


def fs_slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def gallery_base(url):
    """Normalize a pasted URL to .../venue/<slug>/seating/<filter> (no slash/query)."""
    u = url.split("?")[0].rstrip("/")
    m = GALLERY_BASE.search(u)
    return m.group(1) if m else u


def venue_name(gbase):
    m = VENUE_SLUG.search(gbase + "/")
    return unquote(m.group(1).replace("+", " ")) if m else gbase


def dismiss_modal(page):
    for sel in [
        "text=Continue without supporting us",
        "xpath=//*[normalize-space(text())='×']",
        "xpath=//*[normalize-space(text())='✕']",
        "[aria-label='Close']",
    ]:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=2000)
                page.wait_for_timeout(400)
                return True
        except Exception:
            continue
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    return False


def get_html(page, url, wait_ms=WAIT_AFTER_LOAD):
    last = None
    for attempt in range(3):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(wait_ms)
            dismiss_modal(page)
            page.wait_for_timeout(int(REQUEST_DELAY * 1000))
            return page.content()
        except Exception as e:
            last = e
            page.wait_for_timeout(1500 * (attempt + 1))
    print(f"    load failed: {url} ({last})")
    return None


def parse_gallery(html):
    """One record per photo card: section/row/seat (from URL) + member + rating."""
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for a in soup.find_all("a", href=PHOTO_HREF):
        m = PHOTO_HREF.search(a["href"])
        img = a.find("img", src=THUMB_SRC) or a.find("img")
        if not (img and img.get("src")):
            continue
        src = urljoin(BASE, img["src"])
        if src in seen:
            continue
        seen.add(src)
        block = a.find_parent(["li", "div", "article"]) or a.parent
        member, rating = None, None
        if block:
            ml = block.find("a", href=re.compile(r"/member/[^/]+/?"))
            if ml:
                member = ml.get_text(strip=True) or None
            rimg = block.find("img", src=RATING_SVG)
            if rimg:
                rm = RATING_SVG.search(rimg["src"])
                if rm:
                    rating = float(f"{rm.group(1)}.{rm.group(2)}")
        out.append({
            "venue": unquote(m.group(2).replace("+", " ")),
            "section": m.group(3),
            "row": m.group(4),
            "seat": m.group(5),
            "member": member,
            "rating": rating,
            "image_url": src,
            "photo_page": urljoin(BASE, a["href"]),
        })
    return out


def fetch_bytes(page, url):
    """Download a URL via fetch() inside the page (same origin, real cookies)."""
    try:
        b64 = page.evaluate(
            """async (u) => {
                try {
                    const r = await fetch(u);
                    if (!r.ok) return null;
                    const buf = await r.arrayBuffer();
                    const a = new Uint8Array(buf);
                    let s = ''; const chunk = 0x8000;
                    for (let i = 0; i < a.length; i += chunk) {
                        s += String.fromCharCode.apply(null, a.subarray(i, i + chunk));
                    }
                    return btoa(s);
                } catch (e) { return null; }
            }""",
            url,
        )
        return base64.b64decode(b64) if b64 else None
    except Exception:
        return None


def download(page, venue, section, medium_url):
    wallpaper = re.sub(r"/medium/", "/wallpaper/", medium_url)
    data = None
    for u in ([wallpaper] if wallpaper != medium_url else []) + [medium_url]:
        data = fetch_bytes(page, u)
        if data:
            break
    if not data:
        return None
    d = os.path.join(PHOTO_ROOT, fs_slug(venue))
    os.makedirs(d, exist_ok=True)
    fname = os.path.basename(medium_url.split("?")[0]) or "image.jpg"
    path = os.path.join(d, f"{section}__{fname}")
    with open(path, "wb") as f:
        f.write(data)
    return path


def collect_all_pages(page, gbase):
    """Walk every numbered page; page 1 links the LAST page number."""
    first = get_html(page, gbase + "/")
    if not first:
        return []
    photos = parse_gallery(first)
    seen = {p["image_url"] for p in photos}
    nums = [int(n) for n in PAGE_NUM.findall(first)]
    max_page = min(max(nums), MAX_PAGES) if nums else 1
    print(f"    {max_page} page(s); page 1: {len(photos)} photos")
    for n in range(2, max_page + 1):
        html = get_html(page, f"{gbase}?page={n}&")
        if not html:
            continue
        added = 0
        for p in parse_gallery(html):
            if p["image_url"] not in seen:
                seen.add(p["image_url"])
                photos.append(p)
                added += 1
        print(f"    page {n}/{max_page}: +{added} (total {len(photos)})")
    return photos


def scrape(page, url, records, done_urls):
    gbase = gallery_base(url)
    print(f"\n=== {venue_name(gbase)} ===\n  {gbase}/")
    photos = collect_all_pages(page, gbase)
    if not photos:
        print("  no photos found (check the URL)")
        return
    if MAX_PHOTOS:
        photos = photos[:MAX_PHOTOS]
    nsec = len({p["section"] for p in photos})
    print(f"  {len(photos)} photos across {nsec} sections")
    for i, p in enumerate(photos, 1):
        if RESUME and p["image_url"] in done_urls:
            print(f"  [{i}/{len(photos)}] sec {p['section']}: already have")
            continue
        local = download(page, p["venue"], p["section"], p["image_url"]) \
            if DOWNLOAD_IMAGES else None
        records.append({
            "venue": p["venue"],
            "section": p["section"],
            "row": p["row"],
            "seat": p["seat"],
            "member": p["member"],
            "rating": p["rating"],
            "image_url": p["image_url"],
            "photo_page": p["photo_page"],
            "local_path": local,
            "source_page": gbase + "/",
            "captured_at": now(),
        })
        tag = "saved" if local else ("logged" if not DOWNLOAD_IMAGES else "NO FILE")
        print(f"  [{i}/{len(photos)}] sec {p['section']} r{p['row']} s{p['seat']}: {tag}")
        done_urls.add(p["image_url"])


def main():
    if not VENUE_URLS:
        print("Add at least one gallery URL to VENUE_URLS at the top of the file.")
        return

    records = []
    if RESUME and os.path.exists(OUT_MANIFEST):
        try:
            with open(OUT_MANIFEST) as f:
                records = json.load(f)
            print(f"Resuming: {len(records)} photos already in {OUT_MANIFEST}")
        except Exception:
            records = []
    done_urls = {r.get("image_url") for r in records if r.get("image_url")}
    done_urls.discard(None)

    with sync_playwright() as p:
        kw = {"headless": HEADLESS}
        if BROWSER_CHANNEL:
            kw["channel"] = BROWSER_CHANNEL
        browser = p.chromium.launch(**kw)
        page = browser.new_context().new_page()

        for url in VENUE_URLS:
            scrape(page, url, records, done_urls)
            with open(OUT_MANIFEST, "w") as f:
                json.dump(records, f, indent=2)

        print("\nDone. Close the browser window when ready.")
        time.sleep(2)
        browser.close()

    by_venue = {}
    for r in records:
        by_venue.setdefault(r.get("venue"), set()).add(r.get("section"))
    print("\n----- summary -----")
    for v, secs in sorted((k, val) for k, val in by_venue.items() if k):
        n = sum(1 for r in records if r.get("venue") == v)
        print(f"  {v}: {len(secs)} sections, {n} photos")
    print(f"\n{len(records)} photos total -> {OUT_MANIFEST}")


if __name__ == "__main__":
    main()
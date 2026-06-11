import asyncio
import json
import os
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from playwright.async_api import async_playwright, Page


DEFAULT_URL = "https://www.stubhub.com/world-cup-atlanta-tickets-6-15-2026/event/153022393/"
OUTPUT_FILE = "stubhub_seats.json"

ROW_SELECTOR = "[data-listing-id]"


def build_quantity_url(url: str, quantity: int) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    qs["quantity"] = [str(quantity)]
    return urlunparse(parsed._replace(query=urlencode(qs, doseq=True)))


def ask_ticket_count() -> int:
    while True:
        try:
            n = int(input("How many tickets? (1-4): ").strip())
            if 1 <= n <= 4:
                return n
        except ValueError:
            pass
        print("Please enter 1-4.")


def money_to_int(text):
    if not text:
        return None
    m = re.search(r"\$?([\d,]+)", str(text))
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


async def close_popups(page: Page):
    selectors = [
        "button:has-text('Accept')",
        "button:has-text('Accept All')",
        "button:has-text('Agree')",
        "button:has-text('Got it')",
        "[id*='onetrust-accept']",
    ]

    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=800):
                await btn.click()
                await page.wait_for_timeout(500)
        except Exception:
            pass


async def dismiss_ticket_modal(page: Page):
    try:
        await page.wait_for_selector(
            "text='How many tickets?'",
            timeout=10000,
            state="visible",
        )

        print("Ticket modal detected.")

        await page.locator("button:has-text('Continue')").first.click()
        await page.wait_for_timeout(2500)

        print("Clicked Continue.")
        return True

    except Exception as e:
        print(f"No modal / failed to click Continue: {e}")
        return False


async def wait_for_listings(page: Page, timeout_s: int = 90) -> bool:
    for _ in range(timeout_s):
        try:
            count = await page.locator(ROW_SELECTOR).count()
            if count > 0:
                print(f"Listings loaded: {count} rows detected.")
                return True
        except Exception:
            pass

        await page.wait_for_timeout(1000)

    return False


async def scroll_and_click_show_more(page: Page, max_rounds: int = 120):
    prev_count = 0
    stable_rounds = 0

    for i in range(max_rounds):
        result = await page.evaluate("""
        () => {
            const rows = [...document.querySelectorAll('[data-listing-id]')];

            if (rows.length === 0) {
                return { ok: false, reason: "no rows" };
            }

            const lastRow = rows[rows.length - 1];
            lastRow.scrollIntoView({ block: "end", behavior: "instant" });

            let p = lastRow.parentElement;
            let scrollTarget = null;

            while (p) {
                if (p.scrollHeight > p.clientHeight + 100) {
                    scrollTarget = p;
                    break;
                }
                p = p.parentElement;
            }

            if (!scrollTarget) {
                scrollTarget = document.scrollingElement || document.documentElement;
            }

            const before = scrollTarget.scrollTop;
            scrollTarget.scrollTop += 1600;
            scrollTarget.dispatchEvent(new Event("scroll", { bubbles: true }));

            return {
                ok: true,
                rows: rows.length,
                before,
                after: scrollTarget.scrollTop,
                scrollHeight: scrollTarget.scrollHeight,
                clientHeight: scrollTarget.clientHeight,
                className: String(scrollTarget.className).slice(0, 120)
            };
        }
        """)

        print(f"Scroll {i + 1}: {result}")
        await page.wait_for_timeout(1200)

        show_more_clicked = False

        try:
            clicked = await page.evaluate("""
            () => {
                const buttons = [...document.querySelectorAll("button")];
                const btn = buttons.find(
                    b => b.innerText && b.innerText.includes("Show more")
                );

                if (!btn) return false;

                btn.scrollIntoView({ block: "center", behavior: "instant" });
                btn.click();
                return true;
            }
            """)

            if clicked:
                show_more_clicked = True
                print("Clicked Show more.")
                await page.wait_for_timeout(3000)

        except Exception as e:
            print(f"Show more click failed: {e}")

        count = await page.locator(ROW_SELECTOR).count()
        print(f"Round {i + 1}: rows={count}, show_more_clicked={show_more_clicked}")

        if count == prev_count and not show_more_clicked:
            stable_rounds += 1
            if stable_rounds >= 5:
                print("Finished loading.")
                break
        else:
            stable_rounds = 0

        prev_count = count


def empty_listing_schema() -> dict:
    return {
        "source": "stubhub",

        "listing_id": None,
        "feature_id": None,

        "section": None,
        "section_type": None,

        "row": None,
        "seat_start": None,
        "seat_end": None,

        "ticket_count": None,
        "availability": None,

        "price": None,
        "original_price": None,
        "data_price": None,

        "rating": None,
        "rating_text": None,

        "view": None,

        "badges": [],
        "notes": [],

        "raw": None,
    }


def parse_listing_text(raw: str) -> dict:
    lines = [x.strip() for x in raw.split("\n") if x.strip()]
    item = empty_listing_schema()
    item["raw"] = " | ".join(lines)

    badge_keywords = [
        "fan favorite",
        "best price",
        "best deal",
        "last tickets",
        "last ticket",
        "hidden gem",
    ]

    note_keywords = [
        "front row of section",
        "second row of section",
        "third row of section",
        "under 15s",
        "under 16s",
        "under 18",
        "over 18",
        "accompanied by an adult",
    ]

    for line in lines:
        lower = line.lower()

        if line.startswith("Section "):
            clean = line.replace("Section ", "", 1).strip()

            if clean.lower().startswith("category"):
                item["section_type"] = "category"
                item["section"] = clean
            else:
                item["section_type"] = "section"
                item["section"] = clean

        elif "supporters" in lower and item["section"] is None:
            item["section_type"] = "supporters"
            item["section"] = line

        if line.startswith("Row"):
            m = re.search(r"Row\s+([A-Za-z0-9]+)", line)
            if m:
                row_value = m.group(1)
                item["row"] = int(row_value) if row_value.isdigit() else row_value

            m = re.search(r"Seats\s+(\d+)\s*-\s*(\d+)", line)
            if m:
                item["seat_start"] = int(m.group(1))
                item["seat_end"] = int(m.group(2))

        m = re.search(r"(\d+)\s+tickets?\s+together", line, re.I)
        if m:
            item["ticket_count"] = int(m.group(1))

        m = re.search(r"Only\s+(\d+)\s+left", line, re.I)
        if m:
            item["availability"] = int(m.group(1))

        prices = re.findall(r"\$([\d,]+)", line)
        if prices:
            parsed_prices = [int(p.replace(",", "")) for p in prices]

            if len(parsed_prices) >= 2:
                item["original_price"] = parsed_prices[0]
                item["price"] = parsed_prices[-1]
            elif item["price"] is None:
                item["price"] = parsed_prices[0]

        if "clear view" in lower:
            item["view"] = "Clear View"
        elif "obstructed" in lower:
            item["view"] = "Obstructed View"
        elif "limited view" in lower:
            item["view"] = "Limited View"

        m = re.search(r"(\d+\.\d+)\s+(Amazing|Great|Good|Fair|Poor)", line, re.I)
        if m:
            item["rating"] = float(m.group(1))
            item["rating_text"] = m.group(2).title()

        for badge in badge_keywords:
            if badge in lower:
                normalized = badge.title()
                if normalized not in item["badges"]:
                    item["badges"].append(normalized)

        if lower in ["amazing", "great", "good", "fair", "poor"]:
            if line.title() not in item["badges"]:
                item["badges"].append(line.title())

        for note in note_keywords:
            if note in lower:
                if line not in item["notes"]:
                    item["notes"].append(line)

    return item


async def extract_seats(page: Page):
    rows = page.locator(ROW_SELECTOR)
    count = await rows.count()

    print(f"Extracting {count} rows.")

    seats = []

    for i in range(count):
        try:
            row = rows.nth(i)

            listing_id = await row.get_attribute("data-listing-id")
            feature_id = await row.get_attribute("data-feature-id")
            data_price = await row.get_attribute("data-price")

            raw_text = await row.inner_text()
            item = parse_listing_text(raw_text)

            item["listing_id"] = listing_id
            item["feature_id"] = feature_id
            item["data_price"] = money_to_int(data_price)

            if item["price"] is None and item["data_price"] is not None:
                item["price"] = item["data_price"]

            seats.append(item)

        except Exception as e:
            print(f"Failed row {i}: {e}")

    return seats


async def extract_event_metadata(page: Page, target_url: str, ticket_count: int) -> dict:
    metadata = {
        "source": "stubhub",
        "event_url": target_url,
        "requested_quantity": ticket_count,

        "event_id": None,
        "event_name": None,
        "event_type": None,

        "venue": None,
        "city": None,
        "state": None,
        "country": None,

        "date": None,
        "time": None,
        "datetime_text": None,

        "currency": "USD",

        "page_title": None,
        "page_description": None,
    }

    try:
        metadata["page_title"] = await page.locator("title").inner_text()
    except Exception:
        pass

    try:
        metadata["page_description"] = await page.locator("meta[name='description']").get_attribute("content")
    except Exception:
        pass

    m = re.search(r"/event/(\d+)/", target_url)
    if m:
        metadata["event_id"] = m.group(1)

    title = metadata["page_title"] or ""
    description = metadata["page_description"] or ""

    if title:
        parts = [p.strip() for p in title.split("|")]

        if parts:
            event_name = parts[0]
            event_name = re.sub(r"\s+Atlanta Tickets$", "", event_name).strip()
            metadata["event_name"] = event_name

        if len(parts) >= 2:
            metadata["date"] = parts[1]

    if description:
        m = re.search(
            r"See\s+(.*?)\s+live at\s+(.*?)\s+in\s+(.*?)\s+on\s+(.*?),\s+at\s+(.*?)\.",
            description,
            re.I,
        )

        if m:
            metadata["event_name"] = m.group(1).strip()
            metadata["venue"] = m.group(2).strip()
            metadata["city"] = m.group(3).strip()
            metadata["date"] = m.group(4).strip()
            metadata["time"] = m.group(5).strip()
            metadata["datetime_text"] = f"{metadata['date']} {metadata['time']}"

    if metadata["venue"] is None:
        try:
            body_text = await page.locator("body").inner_text()
            m = re.search(
                r"(Mercedes-Benz Stadium),\s*(Atlanta),\s*(Georgia),\s*(USA)",
                body_text,
                re.I,
            )
            if m:
                metadata["venue"] = m.group(1)
                metadata["city"] = m.group(2)
                metadata["state"] = m.group(3)
                metadata["country"] = m.group(4)
        except Exception:
            pass

    if metadata["city"] == "Atlanta":
        metadata["state"] = metadata["state"] or "Georgia"
        metadata["country"] = metadata["country"] or "USA"

    if "World Cup" in (metadata["event_name"] or title):
        metadata["event_type"] = "World Cup"

    return metadata


async def fetch_stubhub(url: str | None = None, qty: int = 2, on_frame=None) -> dict:
    """Scrape StubHub seat inventory for ``url`` at ``qty`` tickets.

    Importable, no console I/O. Returns:
        {"source": "stubhub", "metadata": {...}, "listings": [..seat dicts..]}

    ``on_frame(step:int, png_bytes:bytes, action:str)`` is an optional callback
    invoked after each browser milestone with a screenshot, so a caller can
    stream the headed browser's view to a UI. It must never raise (failures are
    swallowed so they can't break the scrape).
    """
    target_url = build_quantity_url(url or DEFAULT_URL, qty)
    step = {"n": 0}

    async def frame(action: str, page: "Page | None") -> None:
        if on_frame is None or page is None:
            return
        try:
            png = await page.screenshot(type="png")
            on_frame(step["n"], png, action)
            step["n"] += 1
        except Exception:  # noqa: BLE001 - screenshotting must not break the scrape
            pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # resale sites degrade / block under headless
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                # New headless mode: no OS window ever appears (off-screen
                # window-parking still flashes a window on macOS), but it renders
                # through the full browser path — far less bot-detectable than
                # legacy headless. Override with PRICE_BROWSER_ONSCREEN=1 to debug
                # with a real, visible window.
                *(
                    []
                    if os.environ.get("PRICE_BROWSER_ONSCREEN") == "1"
                    else ["--headless=new"]
                ),
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )
        await context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
            """
        )
        page = await context.new_page()
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
            await frame("Opened event page", page)

            await close_popups(page)
            await dismiss_ticket_modal(page)
            await close_popups(page)
            await frame("Dismissed popups", page)

            loaded = await wait_for_listings(page)
            await frame("Listings loaded" if loaded else "No listings found", page)
            if not loaded:
                return {"source": "stubhub", "metadata": {}, "listings": []}

            await scroll_and_click_show_more(page)
            await frame("Loaded all listings", page)

            seats = await extract_seats(page)
            metadata = await extract_event_metadata(
                page=page, target_url=target_url, ticket_count=qty
            )
            await frame(f"Extracted {len(seats)} listings", page)

            return {"source": "stubhub", "metadata": metadata, "listings": seats}
        finally:
            await browser.close()


async def main():
    """CLI entry point (manual run): prompts for quantity, writes JSON file."""
    qty = ask_ticket_count()
    result = await fetch_stubhub(DEFAULT_URL, qty)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"metadata": result["metadata"], "tickets": result["listings"]},
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"Saved {len(result['listings'])} listings to {OUTPUT_FILE}")

    print(f"\nSaved {len(seats)} seats to {OUTPUT_FILE}\n")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
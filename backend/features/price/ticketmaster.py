"""
Ticketmaster Seat Price Scraper - Playwright Version

Install:
  pip install playwright
  playwright install chromium

Run:
  python ticketmaster_scraper.py
"""

import asyncio
import json
import re
from playwright.async_api import async_playwright, Page

from .browser_visibility import offscreen_launch_args


EVENT_URL = "https://www.ticketmaster.com/world-cup-match-59-group-d-inglewood-06-25-2026/event/Z7r9jZ1A7434Z"
OUTPUT_FILE = "ticketmaster_seats.json"

ROW_SELECTOR = "[data-bdd='quick-picks-list-item-resale']"

POPUP_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "[id*='onetrust-accept']",
    "button:has-text('Agree')",
    "button:has-text('Accept')",
    "button:has-text('AGREE')",
    "button:has-text('ACCEPT')",
    "[data-bdd='modal-close']",
    "button[aria-label='Close']",
]


def ask_ticket_count() -> int:
    while True:
        try:
            n = int(input("How many tickets? (1-4): ").strip())
            if 1 <= n <= 4:
                return n
        except ValueError:
            pass
        print("Please enter 1-4.")


async def close_popups(page: Page):
    for sel in POPUP_SELECTORS:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1500):
                await btn.click()
                print(f"Closed popup: {sel}")
                await page.wait_for_timeout(800)
        except Exception:
            pass


async def wait_for_ticket_list(page: Page, timeout_s: int = 90) -> bool:
    for attempt in range(timeout_s // 3):
        if attempt % 5 == 0:
            await close_popups(page)

        try:
            await page.wait_for_selector(
                ROW_SELECTOR,
                timeout=3000,
                state="attached",
            )
            print(f"Ticket list loaded after ~{(attempt + 1) * 3}s")
            return True
        except Exception:
            pass

        content = await page.content()
        if "quick-picks-list-item-resale" in content and "data-price" in content:
            print(f"Ticket data appeared after ~{(attempt + 1) * 3}s")
            return True

        await page.wait_for_timeout(3000)

    return False


async def select_ticket_quantity(page: Page, ticket_count: int):
    label_regex = rf"^{ticket_count}\s+Tickets?$"

    print(f"Selecting {ticket_count} ticket(s)...")

    # 先找当前显示的 1 Ticket / 2 Tickets 按钮
    dropdown = page.locator(
        "button",
        has_text=re.compile(r"^\s*\d+\s+Tickets?\s*$", re.I)
    ).first

    await dropdown.wait_for(state="visible", timeout=20000)
    await dropdown.click()
    await page.wait_for_timeout(1000)

    # debug：保存打开 dropdown 后的页面
    with open("ticketmaster_quantity_dropdown_dump.html", "w", encoding="utf-8") as f:
        f.write(await page.content())

    await page.screenshot(path="ticketmaster_quantity_dropdown.png", full_page=True)

    # 选择目标数量
    option = page.locator(
        "button, div, li, span",
        has_text=re.compile(label_regex, re.I)
    ).last

    await option.wait_for(state="visible", timeout=10000)
    await option.click()

    await page.wait_for_timeout(3000)

    print(f"Selected {ticket_count} ticket(s).")
    return True


async def scroll_load_all(page: Page, max_scrolls: int = 80):
    prev_count = 0
    stable_rounds = 0

    for i in range(max_scrolls):
        await page.evaluate("""
        () => {
            const selectors = [
                '[data-bdd="qp-split-scroll"]',
                '[data-bdd="quick-picks-list"]',
                '[class*="listingContainer"]',
                '[class*="QuickPicks"]',
            ];

            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el && el.scrollHeight > el.clientHeight) {
                    el.scrollTop += 1400;
                    el.dispatchEvent(new Event("scroll", { bubbles: true }));
                    return;
                }
            }

            const candidates = [...document.querySelectorAll("*")]
                .filter(el => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);

                    return (
                        r.left > window.innerWidth * 0.55 &&
                        r.height > 250 &&
                        el.scrollHeight > el.clientHeight + 80 &&
                        ["auto", "scroll"].includes(s.overflowY)
                    );
                })
                .sort((a, b) => b.scrollHeight - a.scrollHeight);

            const el = candidates[0];

            if (el) {
                el.scrollTop += 1400;
                el.dispatchEvent(new Event("scroll", { bubbles: true }));
            } else {
                window.scrollBy(0, 800);
            }
        }
        """)

        await page.wait_for_timeout(1200)

        count = await page.locator(ROW_SELECTOR).count()
        print(f"Scroll {i + 1}/{max_scrolls}: {prev_count} -> {count} tickets")

        if count == prev_count and count > 0:
            stable_rounds += 1
            if stable_rounds >= 4:
                print("All visible tickets loaded.")
                break
        else:
            stable_rounds = 0

        prev_count = count


def empty_listing_schema() -> dict:
    return {
        "source": "ticketmaster",
        "listing_id": None,

        "section": None,
        "section_type": "section",

        "row": None,
        "seat_start": None,
        "seat_end": None,

        "ticket_count": None,
        "availability": None,

        "price": None,
        "original_price": None,
        "data_price": None,

        "ticket_type": None,
        "delivery": None,

        "rating": None,
        "rating_text": None,
        "view": None,

        "badges": [],
        "notes": [],

        "raw": None,
    }


def money_to_float(text):
    if not text:
        return None

    m = re.search(r"\$?([\d,]+(?:\.\d+)?)", str(text))
    if not m:
        return None

    return float(m.group(1).replace(",", ""))


def parse_ticketmaster_row(raw: str, data_price: str = None) -> dict:
    lines = [x.strip() for x in raw.split("\n") if x.strip()]
    item = empty_listing_schema()
    item["raw"] = " | ".join(lines)

    if data_price:
        item["data_price"] = money_to_float(data_price)
        item["price"] = item["data_price"]

    for line in lines:
        lower = line.lower()

        if "sec" in lower and "row" in lower:
            parts = [p.strip() for p in line.replace("•", "|").split("|")]

            for part in parts:
                p_lower = part.lower()

                if p_lower.startswith("sec"):
                    item["section"] = part.replace("Sec", "").strip()

                elif p_lower.startswith("row"):
                    row_text = part.replace("Row", "").strip()
                    item["row"] = int(row_text) if row_text.isdigit() else row_text

        elif "resale ticket" in lower or "standard ticket" in lower:
            item["ticket_type"] = line

        elif "mobile" in lower or "entry" in lower or "delivery" in lower:
            item["delivery"] = line

        elif "$" in line and item["price"] is None:
            item["price"] = money_to_float(line)

    return item


async def extract_seats(page: Page, ticket_count: int) -> list[dict]:
    rows = page.locator(ROW_SELECTOR)
    count = await rows.count()

    print(f"Found {count} ticket listings")

    seats = []

    for i in range(count):
        try:
            row = rows.nth(i)

            data_price = await row.get_attribute("data-price")
            listing_id = await row.get_attribute("data-listing-id")

            raw_text = await row.inner_text()
            item = parse_ticketmaster_row(raw_text, data_price)

            item["listing_id"] = listing_id
            item["ticket_count"] = ticket_count

            seats.append(item)

        except Exception as e:
            print(f"Error parsing row {i}: {e}")

    return seats


async def extract_event_metadata(page: Page, ticket_count: int) -> dict:
    metadata = {
        "source": "ticketmaster",
        "event_url": EVENT_URL,
        "requested_quantity": ticket_count,

        "event_id": None,
        "event_name": None,
        "event_type": None,

        "venue": None,
        "city": None,
        "state": None,
        "country": "USA",

        "date": None,
        "time": None,
        "datetime_text": None,

        "currency": "USD",

        "page_title": None,
        "page_description": None,
    }

    try:
        metadata["page_title"] = await page.title()
    except Exception:
        pass

    try:
        metadata["page_description"] = await page.locator(
            "meta[name='description']"
        ).get_attribute("content")
    except Exception:
        pass

    m = re.search(r"/event/([^/?#]+)", EVENT_URL)
    if m:
        metadata["event_id"] = m.group(1)

    try:
        body = await page.locator("body").inner_text()

        m = re.search(
            r"(World Cup:.*?)\n(.*?)\n(SoFi Stadium, Inglewood, CA)",
            body,
            re.S,
        )

        if m:
            metadata["event_name"] = m.group(1).strip()
            metadata["datetime_text"] = m.group(2).strip()
            metadata["venue"] = "SoFi Stadium"
            metadata["city"] = "Inglewood"
            metadata["state"] = "CA"

        m_date = re.search(
            r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+·\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})\s+·\s+([\d:]+\s+[AP]M)",
            body,
        )

        if m_date:
            metadata["date"] = m_date.group(2)
            metadata["time"] = m_date.group(3)
            metadata["datetime_text"] = f"{metadata['date']} {metadata['time']}"

    except Exception:
        pass

    if metadata["event_name"] and "World Cup" in metadata["event_name"]:
        metadata["event_type"] = "World Cup"

    return metadata


async def fetch_ticketmaster(url: str | None = None, qty: int = 2, on_frame=None) -> dict:
    """Scrape Ticketmaster resale prices for ``url`` at ``qty`` tickets.

    Importable, no console I/O. Returns:
        {"source": "ticketmaster", "metadata": {...}, "listings": [..]}

    ``on_frame(step:int, png_bytes:bytes, action:str)`` is an optional callback
    invoked after each browser milestone with a screenshot. It must never raise.
    """
    target_url = url or EVENT_URL
    step = {"n": 0}

    async def frame(action: str, page: "Page | None") -> None:
        if on_frame is None or page is None:
            return
        try:
            png = await page.screenshot(type="png")
            on_frame(step["n"], png, action)
            step["n"] += 1
        except Exception:  # noqa: BLE001
            pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # resale sites degrade / block under headless
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                # Headed for accuracy, hidden from the user. Per-OS strategy:
                # headless=new on Windows so no window ever flashes; off-screen
                # window-parking elsewhere. PRICE_BROWSER_ONSCREEN=1 to debug.
                *offscreen_launch_args(),
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        await context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            """
        )
        page = await context.new_page()
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(3000)
            await frame("Opened event page", page)

            await close_popups(page)
            loaded = await wait_for_ticket_list(page)
            await frame("Ticket list loaded" if loaded else "No tickets found", page)
            if not loaded:
                return {"source": "ticketmaster", "metadata": {}, "listings": []}

            await close_popups(page)
            await select_ticket_quantity(page, qty)
            await frame(f"Selected {qty} tickets", page)

            await scroll_load_all(page)
            await frame("Loaded all tickets", page)

            seats = await extract_seats(page, qty)
            metadata = await extract_event_metadata(page, qty)
            await frame(f"Extracted {len(seats)} listings", page)

            return {"source": "ticketmaster", "metadata": metadata, "listings": seats}
        finally:
            await browser.close()


async def main():
    """CLI entry point (manual run): prompts for quantity, writes JSON file."""
    qty = ask_ticket_count()
    result = await fetch_ticketmaster(EVENT_URL, qty)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"metadata": result["metadata"], "tickets": result["listings"]},
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"Saved {len(result['listings'])} tickets to {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
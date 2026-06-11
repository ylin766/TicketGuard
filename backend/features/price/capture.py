"""Capture a single screenshot of an arbitrary page (the buyer's listing).

The buyer's page can be on any site, so the StubHub/Ticketmaster scrapers can't
parse it — but Gemini vision can read a screenshot of it to extract the event +
seat + price. This opens the page headed (off-screen, like the scrapers), grabs
one screenshot via the ``on_frame`` sink, and closes. Best-effort: returns the
PNG bytes or None.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger("ticketguard.price.capture")


async def capture_screenshot(
    url: str,
    on_frame: Optional[Callable[[int, bytes, str], None]] = None,
    action: str = "Reading your ticket page",
) -> Optional[bytes]:
    """Open ``url`` headed/off-screen, return one screenshot's PNG bytes."""
    from playwright.async_api import async_playwright

    from .browser_visibility import offscreen_launch_args

    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        # Per-OS off-screen strategy (headless=new on Windows so no window ever
        # flashes; window-parking elsewhere). PRICE_BROWSER_ONSCREEN=1 to debug.
        *offscreen_launch_args(),
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=args)
        try:
            context = await browser.new_context(
                viewport={"width": 1400, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(2500)
            png = await page.screenshot(type="png")
            if on_frame is not None and png:
                try:
                    on_frame(0, png, action)
                except Exception:  # noqa: BLE001 - sink must never break capture
                    pass
            return png
        except Exception as exc:  # noqa: BLE001 - capture is best-effort
            logger.warning("[price] screenshot capture failed: %s", str(exc)[:140])
            return None
        finally:
            await browser.close()

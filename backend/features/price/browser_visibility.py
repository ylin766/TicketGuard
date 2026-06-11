"""Cross-platform off-screen browser strategy for the price scrapers.

The price scrapers must run *headed* (resale sites degrade or block under
legacy headless), but we never want a real window flashing in the user's face —
they watch our clay viewport instead. The trick to hide that window differs by
OS, and a single hard-coded flag can't satisfy both:

* **Windows**: ``--window-position=-32000,-32000`` still flashes a visible
  window before it parks off-screen. Chromium's *new* headless mode
  (``--headless=new``) never creates an OS window at all, yet still renders
  through the full (non-bot-detectable) browser path. So Windows wants
  ``--headless=new``.
* **macOS / Linux**: the new headless mode has been observed to still flash /
  misbehave for these scrapers, while off-screen window-parking is clean. So
  they want ``--window-position=-32000,-32000``.

This router picks the right flag per platform. Set ``PRICE_BROWSER_ONSCREEN=1``
to disable both (watch a real, visible window for debugging).
"""

from __future__ import annotations

import os
import sys


def offscreen_launch_args() -> list[str]:
    """Return Chromium launch args that hide the window on the current OS.

    Returns an empty list when ``PRICE_BROWSER_ONSCREEN=1`` (debug: show the
    real window). Otherwise routes by platform:

    * Windows -> ``["--headless=new"]`` (no OS window is ever created)
    * everything else -> ``["--window-position=-32000,-32000"]`` (parked off-screen)
    """
    if os.environ.get("PRICE_BROWSER_ONSCREEN") == "1":
        return []
    if sys.platform.startswith("win"):
        return ["--headless=new"]
    return ["--window-position=-32000,-32000"]

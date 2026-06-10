"""Self-cleaning for headed browsers spawned by the security/price flows.

Headed browsers are launched OFF-SCREEN (so nothing flashes at the user), which
means a leaked one is invisible — it silently piles up Chromium processes. The
graceful per-session teardown (``BrowserSession.kill`` / Playwright
``browser.close``) covers the normal and exception paths, but **cannot** run if
the whole Python process is killed mid-flight.

This module adds a process-level safety net: it kills every Playwright-Chromium
process that descends from THIS Python process when the interpreter exits or
receives a termination signal. Scoping to our own descendants means we never
touch a developer's real Chrome or another app's browser.
"""

from __future__ import annotations

import atexit
import logging
import os
import signal

logger = logging.getLogger("ticketguard.browser_cleanup")

# Path fragments that identify a browser binary WE launched via Playwright.
_PLAYWRIGHT_MARKERS = ("ms-playwright", "playwright")
_CHROMIUM_NAMES = ("chrome", "chromium", "chrome.exe", "chromium.exe", "headless_shell")

_installed = False


def _is_our_browser(proc) -> bool:
    """True if ``proc`` looks like a Playwright Chromium (not the user's Chrome)."""
    try:
        name = (proc.name() or "").lower()
        if not any(name.startswith(n) for n in _CHROMIUM_NAMES):
            return False
        exe = (proc.exe() or "").lower()
        return any(m in exe for m in _PLAYWRIGHT_MARKERS)
    except Exception:  # noqa: BLE001 - proc may have died / be inaccessible
        return False


def kill_descendant_browsers() -> int:
    """Kill any Playwright-Chromium processes descended from this process.

    Returns the number of processes signalled. Best-effort and never raises.
    """
    try:
        import psutil
    except Exception:  # noqa: BLE001 - psutil is a browser-use dep; absence => no-op
        return 0

    try:
        me = psutil.Process(os.getpid())
        children = me.children(recursive=True)
    except Exception:  # noqa: BLE001
        return 0

    killed = 0
    for proc in children:
        if not _is_our_browser(proc):
            continue
        try:
            proc.kill()
            killed += 1
        except Exception:  # noqa: BLE001 - already gone / no permission
            pass
    if killed:
        logger.info("cleaned up %d leaked playwright browser process(es)", killed)
    return killed


def install_browser_cleanup() -> None:
    """Register atexit + signal handlers that sweep leaked browsers on exit.

    Idempotent: safe to call from multiple entry points (server startup, CLI).
    """
    global _installed
    if _installed:
        return
    _installed = True

    atexit.register(kill_descendant_browsers)

    # Also sweep on the common termination signals so Ctrl-C / kill don't leak.
    def _handler(signum, _frame):  # noqa: ANN001
        try:
            kill_descendant_browsers()
        finally:
            # Restore default and re-raise so normal shutdown still happens.
            try:
                signal.signal(signum, signal.SIG_DFL)
                os.kill(os.getpid(), signum)
            except Exception:  # noqa: BLE001
                pass

    for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            # Not in the main thread, or signal unsupported on this platform.
            pass

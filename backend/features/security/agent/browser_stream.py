"""Security browser-check streaming — plays the Layer-2 agent's exploration live.

The browser security check (``browser_security_check``) drives a headed browser
through a ReAct agent that maps a ticket site's sensitive surfaces. It already
captures a screenshot per observed page; this module bridges those screenshots
into an SSE stream so the frontend can play the agent's investigation in real
time (the same clay viewport the price flow uses), instead of staring at a
spinner for the minutes the agent takes.

Frame contract (each yielded dict is one ``data:`` SSE line):
    {"type":"start","url":str,"agent":"browser_check","ts":float}
    {"type":"frame","step":int,"action":str,"image":"data:image/png;base64,…","ts":float}
    {"type":"done","verdict":str|None,"risk_level":str|None,"risk_score":int|None,
     "summary":str|None,
     "brand":{"claimed_platform":str|None,"domain":str|None,"matches":bool|None,
              "trusted":bool|None,"mismatch_reason":str|None,"off_platform_payment":bool|None},
     "sensitive_surfaces":[{"page_state":str,"reached":bool,"action_types":[str],
                            "requested_inputs":[str]}]}
    {"type":"error","message":str}

Best-effort: any failure becomes an ``error`` frame; the agent itself never
raises (it returns ``unknown_browser_check_failed``).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import AsyncGenerator

logger = logging.getLogger("ticketguard.security.browser_stream")


async def stream_browser_check(url: str, max_actions: int = 8) -> AsyncGenerator[dict, None]:
    """Run the Layer-2 browser check for ``url`` and yield SSE frames live."""
    yield {"type": "start", "url": url, "agent": "browser_check", "ts": time.time()}

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_frame(step: int, png_bytes: bytes, action: str) -> None:
        # Called from the runner's coroutine; hop back onto the event loop.
        b64 = base64.b64encode(png_bytes).decode("ascii")
        frame = {
            "type": "frame",
            "step": step,
            "action": action,
            "image": f"data:image/png;base64,{b64}",
            "ts": time.time(),
        }
        try:
            loop.call_soon_threadsafe(queue.put_nowait, frame)
        except RuntimeError:
            # Loop already closed — drop the frame rather than raise.
            pass

    async def _run() -> dict:
        from .browser_check.browser_security_tool import browser_security_check

        # Headed: resale sites degrade under headless and the whole point is to
        # show the live browser. enable_osint is OFF here — the OSINT reputation
        # subagent runs on its own dedicated stream (osint-stream), so leaving it
        # on would re-run the whole reputation pass and waste ~40-60s per audit.
        return await browser_security_check(
            url,
            max_actions=max_actions,
            headless=False,
            on_frame=on_frame,
            enable_osint=False,
        )

    task = asyncio.create_task(_run())
    try:
        while True:
            if task.done() and queue.empty():
                break
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=0.3)
                yield frame
            except asyncio.TimeoutError:
                continue

        result = await task
        trust = result.get("trust_check") or {}
        claim = result.get("claim") or {}
        surfaces = result.get("sensitive_surfaces") or []
        yield {
            "type": "done",
            "verdict": result.get("verdict"),
            "risk_level": result.get("risk_level"),
            "risk_score": result.get("risk_score"),
            "summary": result.get("summary"),
            # Brand / domain consistency (the "is this really who it claims?" check).
            "brand": {
                "claimed_platform": claim.get("claimed_platform"),
                "claimed_event": claim.get("claimed_event"),
                "domain": trust.get("current_registered_domain"),
                "matches": trust.get("domain_matches_claimed_platform"),
                "trusted": trust.get("is_trusted_marketplace_domain"),
                "mismatch_reason": trust.get("domain_mismatch_reason"),
                "off_platform_payment": trust.get("off_platform_payment_detected"),
            },
            # Sensitive surfaces the agent reached + what each one asks for.
            "sensitive_surfaces": [
                {
                    "page_state": s.get("page_state"),
                    "reached": s.get("reached"),
                    "action_types": s.get("action_types") or [],
                    "requested_inputs": s.get("requested_inputs") or [],
                }
                for s in surfaces
            ],
        }
    except Exception as exc:  # noqa: BLE001 - surface any failure as an error frame
        logger.exception("[security] browser stream failed")
        yield {"type": "error", "message": str(exc)}
    finally:
        # Client disconnected (GeneratorExit) or we errored mid-run: tear down the
        # in-flight browser task so we don't leak an orphaned headed Chromium.
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                logger.info("[security] browser task cancelled on disconnect")

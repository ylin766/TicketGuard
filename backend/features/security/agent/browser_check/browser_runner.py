"""The deterministic browser probe — a bounded, safety-railed state machine.

``BrowserCheckRunner`` drives a single ``browser_use.BrowserSession`` through at
most ``max_click_depth`` purchase-flow transitions, capturing a snapshot at each
step and asking Gemini to (1) extract the page's claim, (2) detect sensitive
actions, and (3) rank the single safest next click. It STOPS the moment a
sensitive page, captcha/error, or depth limit is reached, and it never clicks an
element whose label implies an irreversible action (pay / confirm / accept
transfer / submit code).

The final verdict is produced by ``domain_rules.evaluate_trust_and_score`` — the
LLM only describes; the rules decide.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import logging
import os
import tempfile
import uuid
from typing import Optional

from .domain_rules import evaluate_trust_and_score, registered_domain
from .gemini_client import (
    classify_claim,
    classify_sensitive_action,
    rank_transition,
)
from .schemas import (
    BrowserSecurityResult,
    BrowserSnapshot,
    ClaimExtraction,
    ClickableElement,
    SensitiveActionDetection,
    TransitionRecord,
)

logger = logging.getLogger("ticketguard.browser_check.runner")

# Page states that mean "stop, this is a sensitive decision point".
SENSITIVE_STATES = frozenset(
    {"login_required", "payment_required", "ticket_transfer_claim",
     "off_platform_payment"}
)
HALT_STATES = frozenset({"blocked_or_captcha", "error_page"})

# Never click an element whose label contains any of these — irreversible.
UNSAFE_CLICK_TEXT = (
    "pay", "place order", "confirm purchase", "submit payment", "checkout now",
    "accept transfer", "submit code", "transfer now", "send payment",
    "connect wallet", "complete purchase", "place your order", "buy now",
)

_HARD_DEPTH_CAP = 2          # safety cap regardless of caller request
_NAV_SETTLE_SECONDS = 5.0    # let the page settle after navigate / click
_LOAD_STATE_TIMEOUT_MS = 12000  # cap on waiting for the SPA to finish loading
_MAX_SNAPSHOT_CHARS = 12000


async def _maybe_await(value):
    """Await ``value`` if it is awaitable, else return it as-is."""
    if inspect.isawaitable(value):
        return await value
    return value


def _is_unsafe_label(label: Optional[str]) -> bool:
    """True if a clickable label implies an irreversible/payment action."""
    if not label:
        return False
    low = label.lower()
    return any(bad in low for bad in UNSAFE_CLICK_TEXT)


class BrowserCheckRunner:
    """Bounded, safety-railed browser probe for one ticket URL."""

    def __init__(self, max_click_depth: int = 2):
        self.max_click_depth = max(0, min(max_click_depth, _HARD_DEPTH_CAP))
        self.workdir = tempfile.mkdtemp(prefix="ticket_browser_check_")
        self._session = None

    # ----------------------------------------------------------------- #
    # Public entry points                                               #
    # ----------------------------------------------------------------- #

    def run_sync(self, url: str, **kwargs) -> BrowserSecurityResult:
        """Synchronous wrapper around :meth:`run` (for CLI / non-async callers)."""
        return asyncio.run(self.run(url, **kwargs))

    async def run(
        self,
        url: str,
        expected_event: Optional[str] = None,
        expected_venue: Optional[str] = None,
        expected_date: Optional[str] = None,
    ) -> BrowserSecurityResult:
        """Open ``url``, probe safely, and return the structured risk result.

        Never raises: any failure yields an ``unknown_browser_check_failed``
        result rather than propagating, so the parent agent always gets valid JSON.
        """
        snapshots: list[BrowserSnapshot] = []
        transitions: list[TransitionRecord] = []
        errors: list[str] = []

        try:
            from browser_use import BrowserSession  # lazy: heavy + needs Chromium

            self._session = BrowserSession(headless=True)
            await self._session.start()
            await self._session.navigate(url)
            await self._settle()

            for step in range(self.max_click_depth + 1):
                snapshot = await self._capture_snapshot(step)
                snapshots.append(snapshot)

                claim = classify_claim(
                    snapshot, expected_event, expected_venue, expected_date
                )
                sensitive = classify_sensitive_action(snapshot, claim)

                # --- stop conditions ---
                if sensitive.is_sensitive_action_page or claim.page_state in SENSITIVE_STATES:
                    transitions.append(TransitionRecord(
                        step=step, before_url=snapshot.url,
                        page_state_before=claim.page_state,
                        stopped_reason="Sensitive decision point reached.",
                    ))
                    break
                if claim.page_state in HALT_STATES:
                    transitions.append(TransitionRecord(
                        step=step, before_url=snapshot.url,
                        page_state_before=claim.page_state,
                        stopped_reason=f"Cannot inspect reliably ({claim.page_state}).",
                    ))
                    break
                if step >= self.max_click_depth:
                    transitions.append(TransitionRecord(
                        step=step, before_url=snapshot.url,
                        page_state_before=claim.page_state,
                        stopped_reason="Max click depth reached.",
                    ))
                    break

                # --- choose + safety-gate one click ---
                decision = rank_transition(snapshot, claim, sensitive)
                chosen = self._safe_chosen_element(snapshot, decision)
                if chosen is None:
                    transitions.append(TransitionRecord(
                        step=step, before_url=snapshot.url,
                        clicked_index=decision.chosen_index,
                        clicked_text=decision.action_label,
                        page_state_before=claim.page_state,
                        stopped_reason=(
                            decision.reason
                            if not decision.should_click
                            else f"Click blocked by safety guard: {decision.action_label!r}"
                        ),
                    ))
                    break

                before_url = snapshot.url
                clicked_ok = await self._click_index(chosen.index)
                if not clicked_ok:
                    transitions.append(TransitionRecord(
                        step=step, before_url=before_url,
                        clicked_index=chosen.index, clicked_text=decision.action_label,
                        page_state_before=claim.page_state,
                        stopped_reason="Click failed; element not actionable.",
                    ))
                    break
                await self._settle()

                transitions.append(TransitionRecord(
                    step=step, before_url=before_url,
                    clicked_index=chosen.index, clicked_text=decision.action_label,
                    page_state_before=claim.page_state,
                ))
                # The next loop iteration captures the post-click page as the
                # official next snapshot.

            # --- final verdict from the last snapshot ---
            final_snapshot = snapshots[-1]
            final_claim = classify_claim(
                final_snapshot, expected_event, expected_venue, expected_date
            )
            final_sensitive = classify_sensitive_action(final_snapshot, final_claim)

            # Reconcile after-states into the transition records.
            if transitions and final_snapshot.url:
                transitions[-1].after_url = final_snapshot.url
                transitions[-1].page_state_after = final_claim.page_state

            trust, level, score, verdict, summary, rec, evidence = (
                evaluate_trust_and_score(
                    input_url=url, snapshots=snapshots, claim=final_claim,
                    sensitive=final_sensitive, expected_event=expected_event,
                    expected_venue=expected_venue, expected_date=expected_date,
                )
            )

            return BrowserSecurityResult(
                input_url=url, final_url=final_snapshot.url,
                risk_level=level, risk_score=score, verdict=verdict,
                summary=summary, claim=final_claim, sensitive_action=final_sensitive,
                trust_check=trust, transitions=transitions, evidence=evidence,
                recommended_action=rec, snapshots=snapshots, errors=errors,
            )

        except Exception as exc:  # noqa: BLE001 - never propagate to the agent
            logger.exception("browser check failed: %s", exc)
            errors.append(str(exc))
            return self._failed_result(url, snapshots, errors)
        finally:
            await self._close_session()

    # ----------------------------------------------------------------- #
    # Browser interaction                                               #
    # ----------------------------------------------------------------- #

    async def _settle(self) -> None:
        """Wait for the page to finish rendering before capturing.

        Modern ticket sites are JS SPAs: ``navigate`` returns long before the
        content paints. We best-effort wait for the DOM/network to quiesce, give
        a fixed grace period, and nudge a scroll to trigger lazy-loaded content.
        """
        try:
            page = await _maybe_await(self._session.get_current_page())
            try:
                await page.wait_for_load_state(
                    "domcontentloaded", timeout=_LOAD_STATE_TIMEOUT_MS
                )
            except Exception:  # noqa: BLE001 - load-state wait is best-effort
                pass
            try:
                await page.wait_for_load_state(
                    "networkidle", timeout=_LOAD_STATE_TIMEOUT_MS
                )
            except Exception:  # noqa: BLE001 - networkidle often never fires
                pass
            try:
                await page.evaluate("() => window.scrollBy(0, 600)")
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            logger.debug("settle failed: %s", exc)
        await asyncio.sleep(_NAV_SETTLE_SECONDS)

    async def _capture_snapshot(self, step: int) -> BrowserSnapshot:
        """Observe the current page into a ``BrowserSnapshot``."""
        state = await self._session.get_browser_state_with_recovery(
            cache_clickable_elements_hashes=True, include_screenshot=True
        )
        url = getattr(state, "url", "") or ""
        title = getattr(state, "title", "") or ""

        screenshot_path = self._save_screenshot(step, getattr(state, "screenshot", None))
        clickables = self._build_clickables(getattr(state, "selector_map", {}) or {})
        body_text = await self._body_text()
        html = await self._safe(self._session.get_page_html())

        return BrowserSnapshot(
            step=step,
            url=url,
            registered_domain=registered_domain(url),
            title=title,
            screenshot_path=screenshot_path,
            body_text=(body_text or "")[:_MAX_SNAPSHOT_CHARS],
            html_excerpt=(html or "")[:_MAX_SNAPSHOT_CHARS],
            clickable_elements=clickables,
        )

    def _save_screenshot(self, step: int, screenshot_b64: Optional[str]) -> Optional[str]:
        """Decode a base64 screenshot to a PNG file; return its path or None."""
        if not screenshot_b64:
            return None
        path = os.path.join(self.workdir, f"step_{step}.png")
        try:
            with open(path, "wb") as f:
                f.write(base64.b64decode(screenshot_b64))
            return path
        except Exception as exc:  # noqa: BLE001
            logger.debug("could not save screenshot: %s", exc)
            return None

    def _build_clickables(self, selector_map: dict) -> list[ClickableElement]:
        """Convert a browser_use selector_map into ``ClickableElement`` rows."""
        out: list[ClickableElement] = []
        for idx, node in selector_map.items():
            attrs = getattr(node, "attributes", {}) or {}
            try:
                text = node.get_all_text_till_next_clickable_element()
            except Exception:  # noqa: BLE001
                text = ""
            out.append(ClickableElement(
                index=int(idx),
                text=(text or "").strip()[:160],
                tag=getattr(node, "tag_name", None),
                role=attrs.get("role"),
                aria_label=attrs.get("aria-label"),
                href=attrs.get("href"),
            ))
        return out

    async def _body_text(self) -> str:
        """Best-effort visible body text via the current page's innerText."""
        try:
            page = await _maybe_await(self._session.get_current_page())
            return await page.evaluate(
                "() => document.body ? document.body.innerText : ''"
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("body_text eval failed: %s", exc)
            return ""

    async def _click_index(self, index: int) -> bool:
        """Click the element at ``index`` via its DOM node; True on success."""
        try:
            node = await self._session.get_dom_element_by_index(index)
            if node is None:
                return False
            await self._session._click_element_node(node)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("click failed at index %s: %s", index, exc)
            return False

    def _safe_chosen_element(self, snapshot, decision) -> Optional[ClickableElement]:
        """Resolve the ranker's choice to a concrete element, gated by safety.

        Returns the element only if the model said click, the index exists, and
        neither the model's label nor the element's own text implies an
        irreversible action.
        """
        if not decision.should_click or decision.chosen_index is None:
            return None
        if decision.safety != "safe":
            return None
        if _is_unsafe_label(decision.action_label):
            return None
        for el in snapshot.clickable_elements:
            if el.index == decision.chosen_index:
                if _is_unsafe_label(el.text):
                    return None
                return el
        return None

    async def _safe(self, coro):
        """Await a coroutine, swallowing failures into None."""
        try:
            return await coro
        except Exception as exc:  # noqa: BLE001
            logger.debug("browser call failed: %s", exc)
            return None

    async def _close_session(self) -> None:
        """Tear down the browser session, tolerating any failure."""
        if self._session is None:
            return
        for method_name in ("kill", "close", "stop"):
            method = getattr(self._session, method_name, None)
            if method is None:
                continue
            try:
                await _maybe_await(method())
            except Exception as exc:  # noqa: BLE001 - cleanup must never raise
                logger.debug("session.%s() failed: %s", method_name, exc)
            return

    # ----------------------------------------------------------------- #
    # Failure result                                                    #
    # ----------------------------------------------------------------- #

    def _failed_result(
        self, url: str, snapshots: list[BrowserSnapshot], errors: list[str]
    ) -> BrowserSecurityResult:
        """Build a valid ``unknown`` result when the browser check could not run."""
        final_url = snapshots[-1].url if snapshots else None
        return BrowserSecurityResult(
            input_url=url,
            final_url=final_url,
            risk_level="unknown",
            risk_score=50,
            verdict="unknown_browser_check_failed",
            summary="Browser check failed before reliable evidence could be collected.",
            claim=ClaimExtraction(),
            sensitive_action=SensitiveActionDetection(),
            evidence=[f"Browser check error: {e}" for e in errors] or [
                "Browser check failed for an unknown reason."
            ],
            recommended_action=(
                "Do not rely on the browser result; use manual verification or "
                "the other security modules."
            ),
            snapshots=snapshots,
            errors=errors,
        )

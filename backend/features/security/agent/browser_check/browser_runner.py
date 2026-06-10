"""The browser probe — a guard-railed, agent-driven explorer.

``BrowserCheckRunner`` opens a single ``browser_use.BrowserSession`` and lets an
LLM *agent* drive the exploration: at each step the agent observes the page and
chooses one action — ``click`` (go deeper), ``go_back`` (retreat to probe another
branch), or ``finish`` (it has seen enough). The goal is to surface every
SENSITIVE page the site leads to (login / payment / transfer / off-platform) so
the deterministic rules can judge risk.

The agent decides the *trajectory*; the runner keeps it safe and bounded:
- a hard action budget (``max_actions``, capped at ``_HARD_ACTION_CAP``),
- a visited / already-clicked set so it cannot loop,
- an observe-only safety gate: it never clicks an irreversible label (pay /
  confirm / accept transfer / submit code) and never interacts with a sensitive
  page (only retreats from it).

The final verdict is still produced by ``domain_rules.evaluate_trust_and_score``
— the LLM only explores and describes; the rules decide.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import logging
import os
import tempfile
import uuid
from typing import Callable, Optional

from .rules.domain_rules import evaluate_trust_and_score, is_trusted_domain, registered_domain
from .llm.gemini_client import classify_claim, classify_sensitive_action
from .schemas import (
    BrowserSecurityResult,
    BrowserSnapshot,
    ClaimExtraction,
    ClickableElement,
    SensitiveActionDetection,
    SensitiveSurface,
    TransitionRecord,
)

logger = logging.getLogger("ticketguard.browser_check.runner")

# Page states that mean "stop interacting, this is a sensitive decision point".
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

# Buttons that merely advance / dismiss (consent banners, info modals, "Continue")
# — necessary to load the page, so they are EXEMPT from the repeat-dedup and may be
# re-clicked each time a reload re-shows them.
NECESSARY_BUTTON_TEXT = (
    "accept & continue", "accept and continue", "i accept", "i agree", "got it",
    "accept all", "accept cookies", "no thanks", "continue", "accept", "agree",
    "ok", "okay", "dismiss", "close", "skip", "proceed",
)

# How "security-relevant" each page state is, used to pick the one observation
# fed to the deterministic scorer (the worst surface the agent reached).
_SENSITIVITY_RANK = {
    "off_platform_payment": 5,
    "ticket_transfer_claim": 4,
    "payment_required": 3,
    "login_required": 2,
}

_HARD_ACTION_CAP = 20         # absolute ceiling on agent actions, regardless of caller
_STALL_LIMIT = 3              # consecutive non-progress actions before giving up
_MAX_SIG_REPEAT = 2           # times an ordinary click may repeat before it's redundant
_MAX_NECESSARY_REPEAT = 8     # higher cap for necessary consent/continue buttons
_NAV_SETTLE_SECONDS = 3.0     # fixed grace for late-painting SPA content
_LOAD_STATE_TIMEOUT_MS = 6000   # cap on waiting for domcontentloaded
# networkidle almost never fires on ad/tracker-heavy ticket SPAs, so this wait
# used to burn its full timeout every step — keep it short so it only helps the
# pages that genuinely do go idle quickly.
_NETWORKIDLE_TIMEOUT_MS = 3000
_MAX_SNAPSHOT_CHARS = 12000

# When run on-screen (PRICE_BROWSER_ONSCREEN=1) keep browser-use's default
# top-left window position; off-screen mode runs headless (no window at all).
_DEFAULT_WINDOW_POSITION = {"width": 0, "height": 0}


async def _maybe_await(value):
    """Await ``value`` if it is awaitable, else return it as-is."""
    if inspect.isawaitable(value):
        return await value
    return value


def _playwright_chromium_path() -> Optional[str]:
    """Resolve Playwright's bundled Chromium executable (same as the scrapers).

    browser-use's own browser discovery globs for ``chromium-*/chrome-win/`` but
    current Playwright ships Chromium under ``chrome-win64/``, so that lookup
    misses and browser-use silently falls back to system Edge. Pointing
    ``executable_path`` straight at Playwright's Chromium keeps the probe on the
    exact same browser the price scrapers use. Returns None if it can't resolve.

    Resolved by globbing the ms-playwright cache directly (not via the Playwright
    API, which has a sync/async variant mismatch and would launch a driver) so it
    is safe to call from inside the running event loop.
    """
    import glob

    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "ms-playwright"
    )
    # Newer Playwright uses chrome-win64; older used chrome-win — match both.
    patterns = [
        os.path.join(base, "chromium-*", "chrome-win64", "chrome.exe"),
        os.path.join(base, "chromium-*", "chrome-win", "chrome.exe"),
        os.path.join(base, "chromium-*", "chrome-linux*", "chrome"),
        os.path.join(base, "chromium-*", "chrome-mac*", "Chromium.app",
                     "Contents", "MacOS", "Chromium"),
    ]
    for pat in patterns:
        matches = sorted(glob.glob(pat))
        if matches:
            return matches[-1]  # highest version
    logger.warning("[browser_check] could not resolve Playwright Chromium path")
    return None



def _is_unsafe_label(label: Optional[str]) -> bool:
    """True if a clickable label implies an irreversible/payment action."""
    if not label:
        return False
    low = label.lower()
    return any(bad in low for bad in UNSAFE_CLICK_TEXT)


# Multi-word consent phrases can match anywhere; single words must be (nearly) the
# whole label so "ok" doesn't match "bookmark" and "close" doesn't match "disclose".
_NECESSARY_PHRASES = tuple(p for p in NECESSARY_BUTTON_TEXT if " " in p)
_NECESSARY_WORDS = frozenset(p for p in NECESSARY_BUTTON_TEXT if " " not in p)


def _is_necessary_button(label: Optional[str]) -> bool:
    """True for consent / continue / dismiss buttons that must stay clickable."""
    if not label:
        return False
    low = " ".join(label.lower().split())
    if any(p in low for p in _NECESSARY_PHRASES):
        return True
    return any(low == w or low.startswith(w + " ") for w in _NECESSARY_WORDS)


class BrowserCheckRunner:
    """Guard-railed, agent-driven browser probe for one ticket URL."""

    def __init__(self, max_actions: int = 8, headless: bool = True,
                 on_frame: Optional[Callable[[int, bytes, str], None]] = None):
        self.max_actions = max(1, min(max_actions, _HARD_ACTION_CAP))
        self.headless = headless
        self.workdir = tempfile.mkdtemp(prefix="ticket_browser_check_")
        self._session = None
        # Optional live-frame sink: called as on_frame(step, png_bytes, action)
        # after each page observation so a UI can play the agent's exploration.
        # Must never raise.
        self._on_frame = on_frame
        self._frame_seq = 0

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
        """Open ``url``, let a ReAct agent explore safely, return the risk result.

        A native ADK ``LlmAgent`` drives the exploration by calling the
        ``click_element`` / ``go_back`` / ``finish`` tools; the tools enforce the
        guard rails (budget, dedup, observe-only safety gate). The deterministic
        rules still produce the verdict afterwards.

        Never raises: any failure yields an ``unknown_browser_check_failed``
        result rather than propagating, so the parent agent always gets valid JSON.
        """
        self._reset_state(expected_event, expected_venue, expected_date)
        errors: list[str] = []

        try:
            from browser_use import BrowserSession  # lazy: heavy + needs Chromium

            # Off-screen window parking proved unreliable on Windows (the window
            # still flashed in front of the user), so off-screen mode now runs a
            # real HEADLESS browser: no OS window is ever created, which is the
            # only way to *guarantee* nothing appears on-screen. Screenshots still
            # work headless and feed the clay viewport via on_frame, so the UX is
            # unchanged. Set PRICE_BROWSER_ONSCREEN=1 to debug with a visible,
            # headed window.
            offscreen = os.environ.get("PRICE_BROWSER_ONSCREEN") != "1"
            # Headless when off-screen (no window at all); headed only when the
            # developer explicitly asks to see it.
            headless = True if offscreen else self.headless
            # window_position / off-screen launch args only matter for a real
            # (headed) window; in headless mode there is no window to place.
            window_position = _DEFAULT_WINDOW_POSITION if not headless else None
            launch_args: list[str] = []
            # Force Playwright's bundled Chromium (identical to the scrapers).
            # Without this, browser-use's discovery misses Chromium on Windows
            # and falls back to system Edge.
            chromium_path = _playwright_chromium_path()
            # highlight_elements=False keeps screenshots clean; we draw our own
            # marker around only the element the agent is about to click.
            # enable_default_extensions=False skips downloading/loading uBlock,
            # cookie-consent and ClearURLs add-ons — they add nothing to a
            # read-only fraud probe but make the (headed, Windows) Chromium cold
            # start blow past browser-use's 30s launch timeout.
            session_kwargs = dict(
                headless=headless,
                highlight_elements=False,
                enable_default_extensions=False,
                window_position=window_position,
                args=launch_args,
            )
            if chromium_path:
                session_kwargs["executable_path"] = chromium_path
            self._session = BrowserSession(**session_kwargs)
            await self._session.start()
            await self._session.navigate_to(url)
            await self._settle()

            if not await self._observe_into_state():
                self._transitions.append(TransitionRecord(
                    step=0, before_url=url,
                    stopped_reason="Could not inspect the first page; stopping.",
                ))
            else:
                snapshot, claim, _, _ = self._cur
                # Early gate: not even a ticket site (and not whitelisted/blocked)
                # → short-circuit before spinning up the agent or OSINT.
                if self._short_circuit_non_ticket(claim, snapshot):
                    return self._not_a_ticket_site_result(url, self._snapshots, claim)
                await self._explore_with_agent()

            # --- final verdict: feed the rules the most security-relevant page ---
            final_claim, final_sensitive = self._select_for_verdict(self._observations)

            trust, level, score, verdict, summary, rec, evidence = (
                evaluate_trust_and_score(
                    input_url=url, snapshots=self._snapshots, claim=final_claim,
                    sensitive=final_sensitive, expected_event=expected_event,
                    expected_venue=expected_venue, expected_date=expected_date,
                )
            )
            for s in self._surfaces:
                line = self._surface_evidence_line(s)
                if line not in evidence:
                    evidence.append(line)

            return BrowserSecurityResult(
                input_url=url,
                final_url=(self._snapshots[-1].url if self._snapshots else None),
                risk_level=level, risk_score=score, verdict=verdict,
                summary=summary, claim=final_claim, sensitive_action=final_sensitive,
                trust_check=trust, transitions=self._transitions,
                sensitive_surfaces=self._surfaces, evidence=evidence,
                recommended_action=rec, snapshots=self._snapshots, errors=errors,
            )

        except Exception as exc:  # noqa: BLE001 - never propagate to the agent
            logger.exception("browser check failed: %s", exc)
            errors.append(str(exc))
            return self._failed_result(url, self._snapshots, errors)
        finally:
            await self._close_session()

    # ----------------------------------------------------------------- #
    # ReAct exploration: per-run state, observation, and tools          #
    # ----------------------------------------------------------------- #

    def _reset_state(self, expected_event, expected_venue, expected_date) -> None:
        """Initialise the mutable per-run exploration state the tools share."""
        self._expected = (expected_event, expected_venue, expected_date)
        self._snapshots: list[BrowserSnapshot] = []
        self._observations: list[tuple] = []
        self._transitions: list[TransitionRecord] = []
        self._surfaces: list[SensitiveSurface] = []
        self._nav_stack: list[str] = []
        self._clicked_counts: dict[str, int] = {}
        self._action_count = 0
        self._finished = False
        self._cur: Optional[tuple] = None  # (snapshot, claim, sensitive, restricted)

    async def _observe_into_state(self) -> bool:
        """Capture + classify the current page into shared state; True on success."""
        try:
            snapshot = await self._capture_snapshot(len(self._snapshots))
            claim = classify_claim(snapshot, *self._expected)
            sensitive = classify_sensitive_action(snapshot, claim)
        except Exception as exc:  # noqa: BLE001 - keep partial results
            logger.warning("observe failed: %s", exc)
            return False
        self._snapshots.append(snapshot)
        self._observations.append((snapshot, claim, sensitive))
        at_decision_point = claim.page_state in SENSITIVE_STATES
        restricted = at_decision_point or claim.page_state in HALT_STATES
        if sensitive.is_sensitive_action_page or claim.page_state in SENSITIVE_STATES:
            self._record_surface(
                self._surfaces, snapshot, claim, sensitive, reached=at_decision_point
            )
        self._cur = (snapshot, claim, sensitive, restricted)
        self._emit_frame(snapshot, claim, sensitive)
        return True

    def _emit_frame(self, snapshot, claim, sensitive) -> None:
        """Push the just-observed page to the live-frame sink, if any.

        Best-effort: a missing screenshot or a raising sink never breaks the run.
        """
        if self._on_frame is None:
            return
        b64 = getattr(self, "_last_screenshot_b64", None)
        if not b64:
            return
        # A short, human-readable label of what the agent is looking at.
        state = getattr(claim, "page_state", "") or "page"
        if getattr(sensitive, "is_sensitive_action_page", False):
            action = f"Inspecting sensitive page: {state}"
        else:
            action = f"Observing {state}"
        try:
            png = base64.b64decode(b64)
            self._on_frame(self._frame_seq, png, action)
            self._frame_seq += 1
        except Exception as exc:  # noqa: BLE001 - the sink must never break the probe
            logger.debug("on_frame sink failed: %s", exc)

    def _observe_text(self) -> str:
        """Render the current page for the agent: state + safe click candidates."""
        snapshot, claim, sensitive, restricted = self._cur
        lines = [
            f"URL: {snapshot.url}",
            f"page_state: {claim.page_state}",
            f"sensitive_decision_point: {restricted}",
            f"actions_used: {self._action_count}/{self.max_actions}",
        ]
        if restricted:
            lines.append(
                "You are ON a sensitive/blocked page — it is already recorded; only "
                "go_back or finish are valid here."
            )
        lines.append("Clickable candidates (index -> label):")
        cands = []
        for el in snapshot.clickable_elements[:40]:
            if _is_unsafe_label(el.text):
                continue
            label = (el.text or el.aria_label or el.href or "").strip()[:60]
            cands.append(f"  [{el.index}] {label!r}")
        lines.extend(cands or ["  (no safe candidates)"])
        if self._surfaces:
            lines.append("Sensitive surfaces found so far:")
            lines.extend("  " + self._surface_line(s) for s in self._surfaces)
        return "\n".join(lines)

    async def _explore_with_agent(self) -> None:
        """Drive exploration with a native ADK ReAct agent calling the tools."""
        from google.adk.agents import LlmAgent  # lazy: heavy + needs ADK
        from google.adk.agents.run_config import RunConfig
        from google.adk.runners import InMemoryRunner
        from google.genai import types as genai_types

        from .....core.config import build_gemini_model
        from .llm.prompts import BROWSE_REACT_INSTRUCTION

        agent = LlmAgent(
            name="ticket_browse_explorer",
            model=build_gemini_model(),
            description="Observe-only ticket-page explorer.",
            instruction=BROWSE_REACT_INSTRUCTION,
            tools=self._build_tools(),
        )
        app = "ticket_browse"
        runner = InMemoryRunner(agent=agent, app_name=app)
        session = await runner.session_service.create_session(app_name=app, user_id="browser")
        msg = genai_types.Content(role="user", parts=[genai_types.Part(
            text="Begin exploring this ticket page; map its sensitive surfaces "
                 "(login, checkout/payment, transfer), then finish.\n\n"
                 + self._observe_text()
        )])
        # Hard backstop on top of the per-tool action budget: ~2 model calls per
        # action plus a buffer for the opening and closing turns.
        cfg = RunConfig(max_llm_calls=self.max_actions * 2 + 6)
        try:
            # Consume the full event stream — the agent ends on its own when it
            # calls finish() and emits a summary (or when max_llm_calls is hit).
            # Breaking out early would cancel the ADK generator mid-span.
            async for _event in runner.run_async(
                user_id="browser", session_id=session.id,
                new_message=msg, run_config=cfg,
            ):
                pass
        except Exception as exc:  # noqa: BLE001 - keep partial results
            logger.warning("browse agent run error: %s", exc)
        if not self._finished:
            self._transitions.append(TransitionRecord(
                step=self._action_count,
                before_url=self._cur[0].url if self._cur else "",
                page_state_before=self._cur[1].page_state if self._cur else "unknown",
                stopped_reason="Exploration budget / agent limit reached.",
            ))

    def _build_tools(self) -> list:
        """Build the three closure tools bound to this run's shared state."""
        runner = self

        async def click_element(index: int, reason: str) -> str:
            """Click the candidate element with this index to go one step deeper
            (e.g. into Sign In, a ticket, or Checkout) and observe what it leads to.

            Args:
                index: The index of a clickable candidate from the current page.
                reason: One short sentence on why this advances the investigation.
            """
            return await runner._tool_click(index, reason)

        async def go_back(reason: str) -> str:
            """Return to the previous page to explore a different branch.

            Args:
                reason: One short sentence on why you are retreating.
            """
            return await runner._tool_go_back(reason)

        async def finish(summary: str) -> str:
            """End the exploration once the reachable sensitive surfaces are mapped.

            Args:
                summary: One line stating which sensitive surfaces were observed.
            """
            return await runner._tool_finish(summary)

        return [click_element, go_back, finish]

    async def _tool_click(self, index: int, reason: str) -> str:
        if self._finished:
            return "Exploration is already finished."
        if self._cur is None:
            return "No page loaded. Call finish(summary)."
        snapshot, claim, _, restricted = self._cur
        if self._action_count >= self.max_actions:
            return "Action budget reached. Call finish(summary) now."
        if restricted:
            self._transitions.append(TransitionRecord(
                step=self._action_count, before_url=snapshot.url,
                page_state_before=claim.page_state, reason=reason,
                stopped_reason="Click refused on a sensitive/blocked page.",
            ))
            return ("You are on a sensitive or blocked page — do not interact. "
                    "Call go_back(reason) or finish(summary).")
        el = next((e for e in snapshot.clickable_elements if e.index == index), None)
        if el is None:
            return (f"No clickable candidate with index {index}. Pick an index from "
                    "the listed candidates, or finish.")
        if _is_unsafe_label(el.text) or _is_unsafe_label(reason):
            self._transitions.append(TransitionRecord(
                step=self._action_count, before_url=snapshot.url, clicked_index=index,
                clicked_text=el.text, page_state_before=claim.page_state, reason=reason,
                stopped_reason="Refused irreversible/payment action.",
            ))
            return (f"Refused: element {index} ({el.text!r}) looks irreversible "
                    "(pay/confirm/submit/accept). Never click it. Pick another or finish.")
        sig = self._click_signature(snapshot.url, el)
        cap = _MAX_NECESSARY_REPEAT if _is_necessary_button(el.text) else _MAX_SIG_REPEAT
        if self._clicked_counts.get(sig, 0) >= cap:
            return (f"Already explored {(el.text or 'that link')!r} enough. Pick a "
                    "different branch or finish.")

        self._action_count += 1
        await self._annotate_click(snapshot, index)
        before_url = snapshot.url
        if not await self._click_index(index):
            self._transitions.append(TransitionRecord(
                step=self._action_count, before_url=before_url, clicked_index=index,
                clicked_text=el.text, page_state_before=claim.page_state, reason=reason,
                stopped_reason="Click failed; element not actionable.",
            ))
            return f"Click on {index} failed (not actionable). Try another or finish."
        self._clicked_counts[sig] = self._clicked_counts.get(sig, 0) + 1
        self._nav_stack.append(before_url)
        await self._settle()
        self._transitions.append(TransitionRecord(
            step=self._action_count, before_url=before_url, clicked_index=index,
            clicked_text=el.text, page_state_before=claim.page_state, reason=reason,
        ))
        if not await self._observe_into_state():
            return "Clicked, but the new page could not be inspected. Call finish(summary)."
        return "Clicked. New page:\n" + self._observe_text()

    async def _tool_go_back(self, reason: str) -> str:
        if self._finished:
            return "Exploration is already finished."
        if self._cur is None:
            return "No page loaded. Call finish(summary)."
        snapshot, claim, _, _ = self._cur
        if self._action_count >= self.max_actions:
            return "Action budget reached. Call finish(summary) now."
        if not self._nav_stack:
            return "No previous page to return to. Call finish(summary)."
        self._action_count += 1
        prev = self._nav_stack.pop()
        self._transitions.append(TransitionRecord(
            step=self._action_count, before_url=snapshot.url, clicked_text="<go_back>",
            after_url=prev, page_state_before=claim.page_state, reason=reason,
        ))
        await self._safe(self._session.navigate_to(prev))
        await self._settle()
        if not await self._observe_into_state():
            return "Went back, but the page could not be inspected. Call finish(summary)."
        return "Went back. Page:\n" + self._observe_text()

    async def _tool_finish(self, summary: str) -> str:
        snapshot = self._cur[0] if self._cur else None
        self._transitions.append(TransitionRecord(
            step=self._action_count,
            before_url=snapshot.url if snapshot else "",
            page_state_before=self._cur[1].page_state if self._cur else "unknown",
            reason=summary, stopped_reason=summary or "Agent finished exploration.",
        ))
        self._finished = True
        return "Exploration recorded as finished. Reply with your one-line summary."

    # ----------------------------------------------------------------- #
    # Exploration helpers                                               #
    # ----------------------------------------------------------------- #

    @staticmethod
    def _click_signature(url: str, el: ClickableElement) -> str:
        """A stable per-link key for dedup.

        Prefer href (stable across reloads), then visible text; fall back to
        index+tag so DISTINCT elements that both lack text/href (e.g. image
        ticket cards) don't all collapse onto one empty signature and wrongly
        flag each other as already-explored.
        """
        key = (el.href or "").strip() or (el.text or "").strip()
        if key:
            return f"{url}::{key.lower()[:80]}"
        return f"{url}::#{el.index}:{el.tag or ''}"

    def _safe_browse_click(self, snapshot, decision) -> Optional[ClickableElement]:
        """Resolve the agent's click to a concrete element, gated by safety.

        Returns the element only if the agent chose ``click`` on a safe index
        whose label (and the element's own text) imply no irreversible action.
        """
        if decision.action != "click" or decision.target_index is None:
            return None
        if decision.safety != "safe":
            return None
        if _is_unsafe_label(decision.action_label):
            return None
        for el in snapshot.clickable_elements:
            if el.index == decision.target_index:
                if _is_unsafe_label(el.text):
                    return None
                return el
        return None

    @staticmethod
    def _record_surface(surfaces, snapshot, claim, sensitive, *, reached=False) -> None:
        """Record a sensitive page (de-duplicated by url + state).

        ``reached`` marks that the agent actually navigated *onto* a true
        decision point (vs only seeing a link to one), so we capture what inputs
        it requests. If a surface seen earlier as a mere link is later reached,
        upgrade it in place with the richer observation.
        """
        for s in surfaces:
            if s.url == snapshot.url and s.page_state == claim.page_state:
                if reached and not s.reached:
                    s.reached = True
                    s.requested_inputs = list(sensitive.requested_inputs)
                    s.irreversible_action_visible = sensitive.irreversible_action_visible
                return
        surfaces.append(SensitiveSurface(
            url=snapshot.url,
            page_state=claim.page_state,
            reached=reached,
            action_types=list(sensitive.action_types),
            payment_context=sensitive.payment_context,
            requested_inputs=list(sensitive.requested_inputs),
            irreversible_action_visible=sensitive.irreversible_action_visible,
            evidence=(sensitive.evidence or claim.evidence)[:4],
        ))

    @staticmethod
    def _select_for_verdict(observations) -> tuple:
        """Pick the (claim, sensitive) most worth scoring from all observations.

        Prefers the worst sensitive surface reached; if nothing sensitive was
        seen, falls back to the last (deepest) observation.
        """
        if not observations:
            return ClaimExtraction(), SensitiveActionDetection()

        def severity(obs):
            _, claim, sens = obs
            rank = max(
                _SENSITIVITY_RANK.get(claim.page_state, 0),
                _SENSITIVITY_RANK.get(sens.page_state, 0),
            )
            return (rank, 1 if sens.is_sensitive_action_page else 0, obs[0].step)

        _, best_claim, best_sens = max(observations, key=severity)
        worst_is_benign = (
            _SENSITIVITY_RANK.get(best_claim.page_state, 0) == 0
            and not best_sens.is_sensitive_action_page
        )
        if worst_is_benign:
            _, claim, sens = observations[-1]
            return claim, sens
        return best_claim, best_sens

    @staticmethod
    def _surface_line(s: SensitiveSurface) -> str:
        actions = ",".join(s.action_types) or "n/a"
        tag = "reached" if s.reached else "seen-link"
        inputs = ",".join(s.requested_inputs)
        extra = f" inputs=[{inputs}]" if inputs else ""
        return f"- [{tag}] {s.page_state} @ {s.url} (actions={actions}{extra})"

    @staticmethod
    def _surface_evidence_line(s: SensitiveSurface) -> str:
        """A human-readable line summarizing one observed sensitive surface."""
        if s.reached:
            inp = ", ".join(s.requested_inputs) or "no input fields detected"
            tail = " (irreversible action visible)" if s.irreversible_action_visible else ""
            return f"Reached {s.page_state} page — it requests: {inp}{tail}."
        actions = ", ".join(s.action_types) or "sensitive affordance"
        return f"Observed a {s.page_state} surface exposing {actions} (not entered)."

    @staticmethod
    def _history_line(t: TransitionRecord) -> str:
        if t.clicked_text == "<go_back>":
            return f"went back to {t.after_url}"
        if t.clicked_text:
            return f"clicked {t.clicked_text!r} on {t.before_url}"
        return f"stopped: {t.stopped_reason}"

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
                    "networkidle", timeout=_NETWORKIDLE_TIMEOUT_MS
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
        state = await self._session.get_browser_state_summary(
            include_screenshot=True
        )
        url = getattr(state, "url", "") or ""
        title = getattr(state, "title", "") or ""

        screenshot_b64 = getattr(state, "screenshot", None)
        self._last_screenshot_b64 = screenshot_b64  # for the live-frame sink
        screenshot_path = self._save_screenshot(step, screenshot_b64)
        # browser-use 0.13: the selector map moved under ``dom_state``.
        dom_state = getattr(state, "dom_state", None)
        selector_map = getattr(dom_state, "selector_map", None) or {}
        clickables = self._build_clickables(selector_map)
        body_text = await self._body_text()

        return BrowserSnapshot(
            step=step,
            url=url,
            registered_domain=registered_domain(url),
            title=title,
            screenshot_path=screenshot_path,
            body_text=(body_text or "")[:_MAX_SNAPSHOT_CHARS],
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
        """Click the element at ``index`` via its DOM node; True on success.

        browser-use 0.13 replaced the direct ``_click_element_node`` helper with
        an event on the session's bus, so we dispatch a ``ClickElementEvent`` and
        await its result.
        """
        try:
            node = await self._session.get_dom_element_by_index(index)
            if node is None:
                return False
            from browser_use.browser.events import ClickElementEvent

            event = self._session.event_bus.dispatch(ClickElementEvent(node=node))
            await event
            await event.event_result(raise_if_any=True, raise_if_none=False)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("click failed at index %s: %s", index, exc)
            return False

    async def _annotate_click(self, snapshot: BrowserSnapshot, index: int) -> None:
        """Draw a red box on this step's screenshot around the element to click.

        Best-effort and never raises: a missing Pillow, bounding box, or file just
        leaves the clean screenshot untouched.
        """
        path = snapshot.screenshot_path
        if not path or not os.path.exists(path):
            return
        try:
            from PIL import Image, ImageDraw  # lazy: optional dependency

            # get_element_by_index resolves through iframes / shadow roots, so the
            # bounding box is correct even for elements a top-level xpath can't see.
            handle = await self._session.get_element_by_index(index)
            if handle is None:
                return
            box = await handle.bounding_box()
            if not box:
                return
            page = await _maybe_await(self._session.get_current_page())
            viewport_w = await page.evaluate("() => window.innerWidth") or box["x"]

            img = Image.open(path).convert("RGB")
            scale = img.width / viewport_w if viewport_w else 1.0
            pad = 5
            x0 = box["x"] * scale - pad
            y0 = box["y"] * scale - pad
            x1 = (box["x"] + box["width"]) * scale + pad
            y1 = (box["y"] + box["height"]) * scale + pad
            draw = ImageDraw.Draw(img)
            draw.rectangle([x0, y0, x1, y1], outline=(255, 0, 0), width=4)
            img.save(path)
        except Exception as exc:  # noqa: BLE001 - annotation is cosmetic
            logger.debug("annotate_click failed at index %s: %s", index, exc)

    async def _safe(self, coro):
        """Await a coroutine, swallowing failures into None."""
        try:
            return await coro
        except Exception as exc:  # noqa: BLE001
            logger.debug("browser call failed: %s", exc)
            return None

    async def _close_session(self) -> None:
        """Tear down the browser session, tolerating any failure.

        Try the most forceful teardown first (``kill``) and only fall back to a
        gentler one if it raises — never stop after the first method merely
        *exists*, or a failed kill would leave the off-screen Chromium orphaned.

        We deliberately do NOT broadly sweep descendant browsers here: price and
        this browser-check can run concurrently, so killing all descendant
        Chromium would take out the price flow's live browser. The process-level
        net (browser_cleanup) handles the "process killed" case at exit.
        """
        if self._session is None:
            return
        for method_name in ("kill", "stop", "close"):
            method = getattr(self._session, method_name, None)
            if method is None:
                continue
            try:
                await _maybe_await(method())
                break
            except Exception as exc:  # noqa: BLE001 - try the next teardown method
                logger.debug("session.%s() failed: %s", method_name, exc)
        self._session = None

    # ----------------------------------------------------------------- #
    # Early gate: not a ticket site                                     #
    # ----------------------------------------------------------------- #

    @staticmethod
    def _short_circuit_non_ticket(claim: ClaimExtraction, snapshot: BrowserSnapshot) -> bool:
        """True when the first page is confidently NOT a ticket-selling site.

        A whitelisted domain is a ticket marketplace by definition, and a
        blocked/captcha/error page is un-judgeable — neither short-circuits.
        """
        if is_trusted_domain(snapshot.registered_domain):
            return False
        if claim.page_state in HALT_STATES:
            return False
        return not claim.is_ticket_site

    def _not_a_ticket_site_result(
        self, url: str, snapshots: list[BrowserSnapshot], claim: ClaimExtraction
    ) -> BrowserSecurityResult:
        """Out-of-scope result: the page is not a ticket marketplace."""
        snap = snapshots[-1] if snapshots else None
        domain = (snap.registered_domain if snap else None) or registered_domain(url) or "This page"
        return BrowserSecurityResult(
            input_url=url,
            final_url=(snap.url if snap else None),
            is_ticket_site=False,
            risk_level="low",
            risk_score=0,
            verdict="not_a_ticket_site",
            summary=(
                f"{domain} does not appear to be a ticket-selling site; "
                "ticket-scam inspection was skipped."
            ),
            claim=claim,
            evidence=[
                f"Live registered domain is {domain}",
                "Page is not a ticket-selling marketplace — inspection skipped (out of scope).",
            ],
            recommended_action=(
                "This is not a ticket marketplace — do not attempt a ticket purchase here."
            ),
            snapshots=snapshots,
        )

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

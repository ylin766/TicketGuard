"""OSINT escalation bridge for the browser check.

When the browser probe lands on an UNFAMILIAR domain with NO recognizable brand
claim — ``domain_matches_claimed_platform is None`` and the domain is not a
trusted marketplace — the deterministic ``domain_rules`` have nothing to anchor
on. This module fills that blind spot: it runs the OSINT subagent (web / social
reputation search) on the live domain and folds its trust rating back into the
browser result.

Kept separate from ``domain_rules`` (pure, no I/O) and ``browser_runner`` (the
browser state machine) on purpose. The OSINT agent and ADK runner are imported
lazily so the ``browser_check`` package stays importable without ADK / Vertex
credentials, and any failure degrades gracefully (the original browser verdict
is preserved, with the error recorded on the attached ``OsintVerdict``).
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from ..rules.domain_rules import classify_risk, verdict_for
from ..schemas import BrowserSecurityResult, OsintVerdict

logger = logging.getLogger("ticketguard.browser_check.osint")

_OSINT_APP = "ticketguard_osint_escalation"
_OSINT_USER = "browser_check"

# The OSINT subagent runs through ADK, which has no built-in retry. Gemini 503
# "high demand" spikes are common, and ADK sometimes swallows them into an empty
# report rather than raising, so we retry on either an exception or empty output.
#
# NOTE: 429 RESOURCE_EXHAUSTED (per-minute quota) is deliberately NOT retried —
# its reset window is ~a minute, so a short backoff just burns the next window's
# budget. It still degrades gracefully via the caller's try/except.
_MAX_OSINT_RETRIES = 2
_OSINT_BACKOFF_SECONDS = (3, 8)


def _is_transient(exc: Exception) -> bool:
    """True if the error is a brief server overload worth a quick retry."""
    text = str(exc).lower()
    if "429" in text or "resource_exhausted" in text or "quota" in text:
        return False  # quota: retrying soon is futile and wastes budget
    return any(s in text for s in ("503", "unavailable", "high demand",
                                   "overloaded"))

# Matches "Trust Rating (0-100) ... Score: 35", "Score: 35", "35/100", etc.
_TRUST_RE = re.compile(r"(?:score|trust\s*rating)\D{0,24}(\d{1,3})", re.IGNORECASE)
_FRACTION_RE = re.compile(r"\b(\d{1,3})\s*/\s*100\b")


def should_escalate(result: BrowserSecurityResult) -> bool:
    """True for any NON-whitelisted domain — run OSINT reputation on it.

    The flow is binary by trust: a whitelisted/trusted marketplace skips OSINT
    (and, if blocked, is simply reported as blocked-but-benign). Every other
    domain — known-brand impersonation, an unknown small site, or one that merely
    self-declares its own domain — gets a reputation check, so the final result
    combines the browser findings with an OSINT score even when the browser
    itself was blocked by a captcha.
    """
    if result.verdict == "not_a_ticket_site":
        return False  # out of scope — don't reputation-check a non-ticket site
    tc = result.trust_check
    if tc.is_trusted_marketplace_domain:
        return False
    return bool(tc.current_registered_domain)


def _parse_trust_rating(text: str) -> Optional[int]:
    """Best-effort extract the 0-100 trust rating from the OSINT report."""
    if not text:
        return None
    # The report ends with the verdict, so prefer the last match.
    matches = _TRUST_RE.findall(text) + _FRACTION_RE.findall(text)
    for raw in reversed(matches):
        try:
            n = int(raw)
        except ValueError:
            continue
        if 0 <= n <= 100:
            return n
    return None


async def _run_osint_agent(domain: str) -> str:
    """Invoke the OSINT subagent on ``domain``; return its final report text."""
    from google.adk.runners import InMemoryRunner  # lazy: heavy + needs ADK
    from google.genai import types as genai_types

    from ...osint.subagent import osint_subagent

    runner = InMemoryRunner(agent=osint_subagent, app_name=_OSINT_APP)
    session = await runner.session_service.create_session(
        app_name=_OSINT_APP, user_id=_OSINT_USER
    )
    msg = genai_types.Content(
        role="user",
        parts=[genai_types.Part(
            text=f"Investigate this ticketing website for fraud risk: {domain}"
        )],
    )

    final_text = ""
    async for event in runner.run_async(
        user_id=_OSINT_USER, session_id=session.id, new_message=msg
    ):
        if not getattr(event, "content", None):
            continue
        for part in event.content.parts:
            if getattr(part, "text", None):
                final_text = part.text  # keep the latest -> the final report
    return final_text


async def _run_osint_with_retry(domain: str) -> str:
    """Run the OSINT subagent, retrying transient 503 / empty-report spikes."""
    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_OSINT_RETRIES + 1):
        try:
            report = await _run_osint_agent(domain)
            if report.strip():
                return report
            logger.warning("OSINT returned an empty report for %s (attempt %d)",
                           domain, attempt + 1)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if not _is_transient(exc):
                raise
            logger.warning("OSINT transient error for %s (attempt %d): %s",
                           domain, attempt + 1, str(exc)[:120])
        if attempt < _MAX_OSINT_RETRIES:
            await asyncio.sleep(
                _OSINT_BACKOFF_SECONDS[min(attempt, len(_OSINT_BACKOFF_SECONDS) - 1)]
            )
    if last_exc is not None:
        raise last_exc
    return ""  # all attempts produced an empty report, no exception


def _fold_into_risk(result: BrowserSecurityResult, verdict: OsintVerdict) -> None:
    """Let OSINT reputation drive the risk on an unknown site — never downgrade.

    The browser rules are near-blind on an unrecognized domain, so the OSINT
    trust rating becomes a first-class signal:
        risk_score = max(browser_score, 100 - trust_rating)
    A clean OSINT result therefore cannot lower a risk the browser already
    found, but a hostile reputation can raise it.
    """
    if verdict.trust_rating is None:
        result.evidence.append(
            f"OSINT reputation check could not complete ({verdict.error})."
            if verdict.error
            else "OSINT reputation check ran but returned no parseable trust "
                 "rating; treat this unknown site with caution."
        )
        return

    osint_risk = 100 - verdict.trust_rating
    new_score = max(result.risk_score, osint_risk)
    if new_score != result.risk_score or result.risk_level == "unknown":
        result.risk_score = new_score
        result.risk_level = classify_risk(new_score)
        result.verdict = verdict_for(result.risk_level)
    result.evidence.append(
        f"OSINT reputation rating for {result.trust_check.current_registered_domain}: "
        f"{verdict.trust_rating}/100 (higher = safer)."
    )


async def run_osint(domain: str) -> OsintVerdict:
    """Run the OSINT reputation subagent on ``domain`` and return its verdict.

    Standalone half of :func:`escalate`: it only produces the ``OsintVerdict``
    (and never raises), so a caller can launch it concurrently with the browser
    probe and fold the result in afterwards via :func:`fold_osint`.
    """
    verdict = OsintVerdict(triggered=True)
    try:
        report = await _run_osint_with_retry(domain)
        verdict.report = report
        verdict.trust_rating = _parse_trust_rating(report)
        if not report.strip():
            verdict.error = "OSINT subagent returned no content (model may be overloaded)"
    except Exception as exc:  # noqa: BLE001 - OSINT is best-effort
        logger.warning("OSINT escalation failed for %s: %s", domain, exc)
        verdict.error = str(exc)
    return verdict


def fold_osint(
    result: BrowserSecurityResult, verdict: OsintVerdict
) -> BrowserSecurityResult:
    """Attach ``verdict`` to ``result`` and fold its trust rating into the risk."""
    result.osint = verdict
    _fold_into_risk(result, verdict)
    return result


async def escalate(result: BrowserSecurityResult) -> BrowserSecurityResult:
    """Run OSINT on an unknown-site browser result and fold the verdict in.

    Never raises: any failure attaches an ``OsintVerdict`` with ``error`` set and
    leaves the original browser verdict otherwise intact.
    """
    domain = result.trust_check.current_registered_domain or result.input_url
    return fold_osint(result, await run_osint(domain))

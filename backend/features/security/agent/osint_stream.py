"""OSINT agent streaming — exposes the social/public-opinion investigation
agent's multi-step trace to the frontend over Server-Sent Events.

This is the *contract* the frontend renders against. We run ``osint_subagent``
through an ADK ``InMemoryRunner`` and translate its event stream into a small,
stable set of JSON frames. Every frame is one line of an SSE body:

    data: {"type": ..., ...}\n\n

The trace data we emit (per-step tool calls, token usage, durations) is the
same telemetry OpenInference reports to Arize Phoenix; here we surface it
directly to the client instead of (or in addition to) the Phoenix UI.

Event frames
------------
start        {"type":"start","url":str,"agent":"osint_subagent","ts":float}
thinking     {"type":"thinking","step":int,"text":str}
                The agent's interim reasoning / narration.
tool_call    {"type":"tool_call","step":int,"id":str,"tool":str,
              "label":str,"args":dict,"ts":float}
                The agent invoked an investigation tool.
tool_result  {"type":"tool_result","step":int,"id":str,"tool":str,
              "preview":str,"chars":int,"duration_ms":int,"ok":bool}
                That tool returned; ``preview`` is a truncated snippet.
tokens       {"type":"tokens","step":int,"prompt":int,"completion":int,
              "total":int}
                Token usage for one model turn (cumulative-safe: each frame is
                that turn's own counts).
report       {"type":"report","score":int|null,"tier":str|null,"text":str,
              "fraud_points":[str],"credible_points":[str],
              "sources":[{"url":str,"platform":str}],"judgment":str}
                The final structured investigation report. ``score`` (0-100)
                and ``tier`` are parsed from the rubric when present; the lists
                + ``judgment`` are parsed from the 3-section report so the UI can
                render components instead of one text wall (``text`` is kept for
                the collapsible full report).
done         {"type":"done","stats":{"steps":int,"tool_calls":int,
              "prompt_tokens":int,"completion_tokens":int,"total_tokens":int,
              "duration_ms":int},"phoenix_url":str|null}
error        {"type":"error","message":str}

Tool labels (friendly names for the UI)
---------------------------------------
    search_consumer_reviews   → "Consumer reviews"        (Trustpilot/SiteJabber)
    search_reddit_discussions → "Reddit discussions"
    search_twitter_mentions   → "Twitter / X mentions"
    search_general_opinions   → "Web deep search"         (Tavily)
    read_specific_url         → "Read full page"          (Jina)
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

# Friendly, human-readable labels + the source platform for each tool, so the
# frontend can show meaningful step names without hardcoding the mapping.
TOOL_LABELS: dict[str, dict[str, str]] = {
    "search_consumer_reviews": {"label": "Consumer reviews", "source": "Trustpilot · SiteJabber"},
    "search_reddit_discussions": {"label": "Reddit discussions", "source": "Reddit"},
    "search_twitter_mentions": {"label": "Twitter / X mentions", "source": "Twitter / X"},
    "search_general_opinions": {"label": "Web deep search", "source": "Tavily"},
    "read_specific_url": {"label": "Read full page", "source": "Jina Reader"},
}

_PREVIEW_CHARS = 600
_SCORE_RE = re.compile(r"(?:Score|Trust Rating|Rating)\D{0,12}(\d{1,3})", re.IGNORECASE)
# Explicit "Score: NN" line in the rating section — the authoritative value
# (avoids matching incidental numbers like a "2.6/5" star rating in prose).
_EXPLICIT_SCORE_RE = re.compile(r"Score\D{0,4}(\d{1,3})", re.IGNORECASE)

# --- Structured report parsing -------------------------------------------------
# The agent emits a 3-section markdown report (see OSINT_AGENT_PROMPT
# <output_format>). We parse it into a small, stable contract the frontend can
# render with components instead of dumping one dense wall of text.
_URL_RE = re.compile(r"https?://[^\s`)\]>]+")
_BOLD_LEAD_RE = re.compile(r"\*\*\s*([^*]+?)\s*:?\s*\*\*")
_PLATFORM_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"trustpilot", re.I), "Trustpilot"),
    (re.compile(r"sitejabber", re.I), "SiteJabber"),
    (re.compile(r"reddit", re.I), "Reddit"),
    (re.compile(r"(?:twitter|x)\.com", re.I), "Twitter / X"),
]
# Bold lead-ins that are section headers / scaffolding, not real content points.
_SKIP_POINT_RE = re.compile(
    r"Key Points|Source Assessment|Trust Rating|Original Post|Judgment|Score|Assessment",
    re.I,
)


def _platform_for(url: str) -> str:
    for rx, name in _PLATFORM_RULES:
        if rx.search(url):
            return name
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else "Web"


def _split_sections(text: str) -> dict[str, str]:
    """Slice the report into its fraud / credibility / rating sections by the
    known section markers, tolerating bold/numbered/bracketed header variants."""
    markers = [
        ("fraud", re.compile(r"Key Points", re.I)),
        ("credible", re.compile(r"Source Assessment|Legitimate/Credible|Credible Information", re.I)),
        ("rating", re.compile(r"Trust Rating|Judgment Basis", re.I)),
    ]
    found: list[tuple[int, str]] = []
    for key, rx in markers:
        m = rx.search(text)
        if m:
            found.append((m.start(), key))
    found.sort()
    out: dict[str, str] = {}
    for i, (pos, key) in enumerate(found):
        end = found[i + 1][0] if i + 1 < len(found) else len(text)
        out[key] = text[pos:end]
    return out


def _extract_points(section: str, limit: int = 6) -> list[str]:
    """Pull the bold lead-in pattern names from a section (the concise headline
    of each bullet), skipping scaffolding labels."""
    points: list[str] = []
    for m in _BOLD_LEAD_RE.finditer(section):
        t = m.group(1).strip().strip(":").strip()
        if not t or _SKIP_POINT_RE.search(t):
            continue
        if t not in points:
            points.append(t)
    return points[:limit]


def _extract_sources(text: str, limit: int = 8) -> list[dict]:
    """Collect unique evidence URLs with their platform label."""
    seen: set[str] = set()
    out: list[dict] = []
    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(".,);")
        if url in seen:
            continue
        seen.add(url)
        out.append({"url": url, "platform": _platform_for(url)})
        if len(out) >= limit:
            break
    return out


def _extract_judgment(rating_section: str) -> str:
    """The 'Judgment Basis' prose — the report's bottom-line takeaway."""
    m = re.search(r"Judgment Basis(.+)", rating_section, re.I | re.S)
    if not m:
        return ""
    body = re.sub(r"\s+", " ", m.group(1)).strip()
    # Strip leading markdown / punctuation scaffolding left after the label
    # (e.g. "**Judgment Basis:**" leaves ":**").
    body = body.lstrip("*:) ").strip()
    return body[:700]


def _tier_for(score: int) -> str:
    """Map a 0-100 trust score to its rubric tier (mirrors OSINT_AGENT_PROMPT)."""
    if score <= 20:
        return "Critical Risk"
    if score <= 40:
        return "High Risk"
    if score <= 60:
        return "Mixed Reliability"
    if score <= 80:
        return "Generally Safe"
    return "Completely Safe"


def _parse_report(text: str) -> dict:
    """Extract the trust score + tier and a structured breakdown from the
    agent's final report text, so the frontend can render components instead of
    one dense text wall. ``text`` is kept for the collapsible full report."""
    score: int | None = None
    sections = _split_sections(text)
    # Prefer the explicit "Score: NN" in the rating section over a loose global
    # match (prose like a "2.6/5" star rating must not be mistaken for a score).
    rating_section = sections.get("rating", "")
    for candidate, rx in ((rating_section, _EXPLICIT_SCORE_RE), (text, _SCORE_RE)):
        m = rx.search(candidate) if candidate else None
        if m:
            val = int(m.group(1))
            if 0 <= val <= 100:
                score = val
                break
    tier = _tier_for(score) if score is not None else None
    return {
        "type": "report",
        "score": score,
        "tier": tier,
        "text": text,
        "fraud_points": _extract_points(sections.get("fraud", "")),
        "credible_points": _extract_points(sections.get("credible", "")),
        "sources": _extract_sources(text),
        "judgment": _extract_judgment(sections.get("rating", "")),
    }


def _maybe_setup_phoenix() -> str | None:
    """Backwards-compatible shim: telemetry is now bootstrapped centrally at
    server startup (see ``backend.observability.telemetry``). This just returns
    the Phoenix workspace URL (initializing on first use if startup hasn't run,
    e.g. in a standalone test harness)."""
    from ....observability.telemetry import init_telemetry

    return init_telemetry()


async def stream_osint(url: str) -> AsyncGenerator[dict, None]:
    """Run the OSINT subagent and yield trace frames as it investigates.

    Yields plain dicts (see module docstring for the frame contract); the
    server layer serializes each as one SSE ``data:`` line.
    """
    phoenix_url = _maybe_setup_phoenix()

    # Import ADK lazily so the rest of the server starts even without GenAI deps.
    try:
        from google.adk.runners import InMemoryRunner
        from google.genai import types as genai_types
        from .osint.subagent import osint_subagent
    except Exception as exc:  # noqa: BLE001
        logger.exception("[OSINT] failed to import agent stack")
        yield {"type": "error", "message": f"Agent unavailable: {exc}"}
        return

    started = time.monotonic()
    yield {"type": "start", "url": url, "agent": "osint_subagent", "ts": time.time()}

    step = 0
    tool_calls = 0
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    # id -> start time, to measure each tool's own latency.
    pending: dict[str, float] = {}
    final_text = ""

    try:
        runner = InMemoryRunner(agent=osint_subagent, app_name="osint")
        session = await runner.session_service.create_session(
            app_name="osint", user_id="web"
        )
        user_msg = genai_types.Content(
            role="user",
            parts=[
                genai_types.Part(
                    text=f"Investigate this ticketing website for fraud risk: {url}"
                )
            ],
        )

        async for event in runner.run_async(
            user_id="web", session_id=session.id, new_message=user_msg
        ):
            # Token usage for this model turn, if reported.
            usage = getattr(event, "usage_metadata", None)
            if usage is not None:
                p = getattr(usage, "prompt_token_count", 0) or 0
                c = getattr(usage, "candidates_token_count", 0) or 0
                t = getattr(usage, "total_token_count", 0) or (p + c)
                if p or c or t:
                    prompt_tokens += p
                    completion_tokens += c
                    total_tokens += t
                    step += 1
                    yield {
                        "type": "tokens",
                        "step": step,
                        "prompt": p,
                        "completion": c,
                        "total": t,
                    }

            content = getattr(event, "content", None)
            if not content or not getattr(content, "parts", None):
                continue

            for part in content.parts:
                text = getattr(part, "text", None)
                fc = getattr(part, "function_call", None)
                fr = getattr(part, "function_response", None)

                if text:
                    final_text = text  # last text part is the report
                    step += 1
                    yield {"type": "thinking", "step": step, "text": text}

                if fc:
                    tool_calls += 1
                    step += 1
                    call_id = getattr(fc, "id", None) or f"call-{tool_calls}"
                    pending[fc.name] = time.monotonic()
                    pending[call_id] = pending[fc.name]
                    meta = TOOL_LABELS.get(fc.name, {"label": fc.name, "source": ""})
                    yield {
                        "type": "tool_call",
                        "step": step,
                        "id": call_id,
                        "tool": fc.name,
                        "label": meta["label"],
                        "source": meta["source"],
                        "args": dict(fc.args or {}),
                        "ts": time.time(),
                    }

                if fr:
                    step += 1
                    call_id = getattr(fr, "id", None) or fr.name
                    start_t = pending.pop(call_id, None) or pending.pop(fr.name, None)
                    duration_ms = (
                        int((time.monotonic() - start_t) * 1000) if start_t else 0
                    )
                    resp = fr.response
                    resp_str = str(resp)
                    ok = "exception" not in resp_str.lower() and "failed" not in resp_str.lower()
                    yield {
                        "type": "tool_result",
                        "step": step,
                        "id": call_id,
                        "tool": fr.name,
                        "preview": resp_str[:_PREVIEW_CHARS],
                        "chars": len(resp_str),
                        "duration_ms": duration_ms,
                        "ok": ok,
                    }

        if final_text:
            yield _parse_report(final_text)

        yield {
            "type": "done",
            "stats": {
                "steps": step,
                "tool_calls": tool_calls,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
            "phoenix_url": phoenix_url,
        }
    except Exception as exc:  # noqa: BLE001 - surface any runtime failure to the client
        logger.exception("[OSINT] stream failed")
        yield {"type": "error", "message": str(exc)}

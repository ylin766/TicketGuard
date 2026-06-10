"""Standalone FastAPI server for TicketGuard custom endpoints.

Exposes:
    POST /api/threat-intel         → blocking, threat-intel pipeline only
    GET  /api/threat-intel/stream  → SSE stream, yields one source per event
    POST /api/security/audit       → full flow: pipeline → score → grey-zone → agent
    GET  /api/osint/stream         → SSE stream, the social/opinion agent's
                                     multi-step trace (tool calls, tokens, time)

Run from the project root (GG Cloud Hackathon/):
    uvicorn backend.server.app:app --port 8001 --reload
"""

import json
import logging
import asyncio
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..features.security.orchestrator import run_security_audit
from ..features.security.pipeline import run_pipeline
from ..features.security.pipeline.threatintel import stream_threatintel
from ..features.security.agent.osint_stream import stream_osint

_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

logger = logging.getLogger(__name__)

app = FastAPI(title="TicketGuard API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    # Vite picks the next free port (5173/5174/5175…) so allow the local range.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):51(7[3-9]|8[0-9])",
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type"],
)


class ThreatIntelRequest(BaseModel):
    url: str


@app.post("/api/threat-intel")
async def threat_intel(req: ThreatIntelRequest) -> dict:
    """Blocking endpoint — returns the full result once all sources complete."""
    result = await asyncio.to_thread(run_pipeline, req.url)
    return result


@app.post("/api/security/audit")
async def security_audit(req: ThreatIntelRequest) -> dict:
    """Full security audit for one URL — what the frontend calls on click.

    Runs the threat-intel pipeline, synthesizes the credibility score, and only
    in the grey zone escalates to the browser + OSINT agent. Returns the pipeline
    result enriched with ``score`` / ``risk_level`` / ``grey_zone`` and, when the
    agent ran, ``agent_audit``.

    NOTE: this is blocking and can take a few minutes when the grey zone triggers
    the agent (real browser exploration). The client must use a long timeout, or
    show progress via ``/api/threat-intel/stream`` first and call this after.
    """
    return await run_security_audit(req.url)


@app.get("/api/threat-intel/stream")
async def threat_intel_stream(url: str) -> StreamingResponse:
    """SSE streaming endpoint — yields one JSON event per source as it completes.

    Event format (text/event-stream):
        data: {"type": "source", "data": { name, threat, detail, ... }}\n\n
        data: {"type": "done",   "status": "ok"|"unavailable", "flagged": bool}\n\n
    """
    async def event_generator():
        # stream_threatintel is a sync generator; run it in a thread
        # and yield each event to the SSE stream.
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def run_in_thread():
            for event in stream_threatintel(url):
                loop.call_soon_threadsafe(queue.put_nowait, event)
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

        asyncio.get_event_loop().run_in_executor(None, run_in_thread)

        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/osint/stream")
async def osint_stream(url: str) -> StreamingResponse:
    """SSE stream of the social/public-opinion OSINT agent's investigation.

    Surfaces the agent's multi-step trace as it runs — interim reasoning, each
    tool call + its result, per-turn token usage, and timing — followed by the
    final structured report and aggregate stats. This is the same telemetry
    OpenInference reports to Arize Phoenix, exposed directly to the client.

    Event format (text/event-stream), see osint_stream.stream_osint for the
    full frame contract:
        data: {"type":"start", ...}\n\n
        data: {"type":"tool_call", "tool":..., "args":..., ...}\n\n
        data: {"type":"tool_result", "preview":..., "duration_ms":..., ...}\n\n
        data: {"type":"tokens", "prompt":..., "completion":..., "total":...}\n\n
        data: {"type":"report", "score":..., "tier":..., "text":...}\n\n
        data: {"type":"done", "stats":{...}, "phoenix_url":...}\n\n
    """

    async def event_generator():
        try:
            async for event in stream_osint(url):
                yield f"data: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:  # client disconnected
            raise
        except Exception as exc:  # noqa: BLE001 - last-resort error frame
            logger.exception("OSINT stream error")
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

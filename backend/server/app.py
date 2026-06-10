"""Standalone FastAPI server for TicketGuard custom endpoints.

Exposes:
    POST /api/threat-intel         → blocking, threat-intel pipeline only
    GET  /api/threat-intel/stream  → SSE stream, yields one source per event
    POST /api/security/audit       → full flow: pipeline → score → grey-zone → agent

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

_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

logger = logging.getLogger(__name__)

app = FastAPI(title="TicketGuard API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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

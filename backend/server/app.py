"""Standalone FastAPI server for TicketGuard custom endpoints.

Exposes a single route:
    POST /api/threat-intel   →  run the deterministic pipeline and return raw results.

Run from the project root (GG Cloud Hackathon/):
    uvicorn backend.server.app:app --port 8001 --reload

The ADK agent UI (adk web) runs separately on port 8000.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..features.security.pipeline import run_pipeline

# Load .env from the backend directory so API keys are available.
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

logger = logging.getLogger(__name__)

app = FastAPI(title="TicketGuard API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


class ThreatIntelRequest(BaseModel):
    url: str


@app.post("/api/threat-intel")
async def threat_intel(req: ThreatIntelRequest) -> dict:
    """Run the deterministic threat-intel pipeline for the given URL.

    Returns the raw pipeline result:
        {
            "status": "ok" | "unavailable",
            "flagged": bool,
            "findings": [ { name, threat, detail, ...source-native fields } ],
            "context":  [ { name, threat: null, detail, ...source-native fields } ],
            "detail": str,
        }
    """
    import asyncio

    result = await asyncio.to_thread(run_pipeline, req.url)
    return result

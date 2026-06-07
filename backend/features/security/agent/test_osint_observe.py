"""
Standalone test: run osint_subagent and log traces to Arize Phoenix Cloud.

Usage:
    cd "GG Cloud Hackathon"
    python3 -m backend.features.security.agent.test_osint_observe
"""

import asyncio
import json
import os
import time
import uuid

import requests

# ── 1. Load .env ─────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv("/Users/ylin766/Downloads/GG Cloud Hackathon/backend/.env")

os.environ["GOOGLE_CLOUD_PROJECT"] = os.environ.get("GOOGLE_CLOUD_PROJECT", "project-8b1e7f0e-3e19-424c-afa")
os.environ["GOOGLE_CLOUD_LOCATION"] = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1"
os.environ.pop("GOOGLE_API_KEY", None)

PHOENIX_API_KEY = os.environ["PHOENIX_API_KEY"]
PHOENIX_ENDPOINT = os.environ.get(
    "PHOENIX_COLLECTOR_ENDPOINT", "https://app.phoenix.arize.com/s/linyushuhong/v1/traces"
)

# ── 2. Bootstrap tracing using raw OTLP/HTTP ─────────────────────────────────
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

otlp_exporter = OTLPSpanExporter(
    endpoint=PHOENIX_ENDPOINT,
    headers={"Authorization": f"Bearer {PHOENIX_API_KEY}"},
)
tracer_provider = TracerProvider()
tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(tracer_provider)

# ── 3. Auto-instrument ADK after TracerProvider is set ──────────────────────
from openinference.instrumentation.google_adk import GoogleADKInstrumentor
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
print(f"[Phoenix] Tracing enabled → {PHOENIX_ENDPOINT}")

# ── 4. Import subagent AFTER instrumentation is active ──────────────────────
from google.adk.runners import InMemoryRunner
from google.genai import types as genai_types
from .osint_subagent import osint_subagent

TARGET_URL = "viagogo.com"


async def run_and_observe():
    runner = InMemoryRunner(agent=osint_subagent, app_name="osint_test")
    session = await runner.session_service.create_session(
        app_name="osint_test", user_id="test_user"
    )

    user_msg = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=f"Investigate this ticketing website for fraud risk: {TARGET_URL}")]
    )

    print(f"\n[Test] Target: {TARGET_URL}")
    print("=" * 60)

    trace_log = []
    step = 0

    async for event in runner.run_async(
        user_id="test_user",
        session_id=session.id,
        new_message=user_msg,
    ):
        if not hasattr(event, "content") or not event.content:
            continue
        for part in event.content.parts:
            if hasattr(part, "text") and part.text:
                step += 1
                print(f"\n[Agent]\n{part.text}")
                trace_log.append({"step": step, "type": "agent_text", "text": part.text})
            if hasattr(part, "function_call") and part.function_call:
                step += 1
                fc = part.function_call
                print(f"\n[→ Tool Call] {fc.name}  args={dict(fc.args)}")
                trace_log.append({"step": step, "type": "tool_call", "tool": fc.name, "args": dict(fc.args)})
            if hasattr(part, "function_response") and part.function_response:
                step += 1
                fr = part.function_response
                preview = str(fr.response)[:600]
                print(f"\n[← Tool Result] {fr.name}:\n{preview}...")
                trace_log.append({"step": step, "type": "tool_result", "tool": fr.name, "result": str(fr.response)})

    print("\n" + "=" * 60)
    print(f"[Done] Open https://app.phoenix.arize.com/s/linyushuhong to view traces.")

    # Flush spans before exit
    tracer_provider.force_flush()


if __name__ == "__main__":
    asyncio.run(run_and_observe())

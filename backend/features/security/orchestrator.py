"""Security orchestrator — orchestrates the whole security workflow.

    page_url (from state)
        |
        v
    pipeline.run_pipeline(url)        # deterministic, hard-coded, no LLM
        |
        v
    write SECURITY_RESULT
        |
        v
    (TODO) grey-zone? --> content_audit_agent   # LLM handles the rest

The deterministic pipeline always runs. The grey-zone LLM agent is not wired in
yet; the escalation branch is left as a placeholder until the score band and the
agent (agent/agent.py) are defined.
"""

import asyncio
import logging
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from typing_extensions import override

from ...core.state_keys import PAGE_URL, SECURITY_RESULT
from .pipeline import run_pipeline

logger = logging.getLogger(__name__)


class SecurityOrchestrator(BaseAgent):
    """Runs the deterministic pipeline, then escalates to the LLM if needed."""

    def __init__(self, name: str):
        super().__init__(name=name)

    def _needs_deep_audit(self, pipeline_result: dict) -> bool:
        """Whether the LLM agent should review this result.

        TODO: define the grey-zone score band and wire in content_audit_agent.
        For now the pipeline verdict is always treated as conclusive.
        """
        return False

    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        url = ctx.session.state.get(PAGE_URL, "")

        # 1. Deterministic pipeline (runs off-thread to avoid blocking the loop).
        pipeline_result = await asyncio.to_thread(run_pipeline, url)
        ctx.session.state[SECURITY_RESULT] = pipeline_result
        logger.info("[%s] pipeline flagged: %s", self.name, pipeline_result.get("flagged"))

        # 2. TODO: grey-zone escalation to content_audit_agent goes here.
        return
        yield  # pragma: no cover - keeps this an async generator


security_orchestrator = SecurityOrchestrator(name="security_orchestrator")

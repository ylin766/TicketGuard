"""OSINT subagent for deep-diving into social media and web sentiment."""

from google.adk.agents import LlmAgent

from .....core.config import build_gemini_model
from .tools import (
    read_specific_url,
    search_consumer_reviews,
    search_general_opinions,
    search_reddit_discussions,
    search_twitter_mentions,
)
from .prompt import OSINT_AGENT_PROMPT

# The investigation tools the subagent may call — shared by the module-level
# singleton and the factory so both stay in sync.
_OSINT_TOOLS = [
    search_consumer_reviews,
    search_reddit_discussions,
    search_twitter_mentions,
    search_general_opinions,
    read_specific_url,
]


def make_osint_subagent(instruction: str | None = None) -> LlmAgent:
    """Build an OSINT subagent with an injectable instruction prompt.

    Production callers use the default prompt; the GEPA training loop passes a
    candidate prompt here so each iteration runs the agent with the prompt being
    optimized, without mutating the shared module-level singleton.
    """
    return LlmAgent(
        name="osint_subagent",
        model=build_gemini_model(),
        instruction=instruction or OSINT_AGENT_PROMPT,
        description="Investigates ticketing URLs using social media, Reddit, Trustpilot, and web searches to detect fraud.",
        tools=_OSINT_TOOLS,
    )


# Default singleton used by production paths (stream, escalation). The factory
# above is for training, where the prompt varies per candidate.
osint_subagent = make_osint_subagent()

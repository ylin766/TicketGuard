"""OSINT subagent for deep-diving into social media and web sentiment."""

from google.adk.agents import LlmAgent

from .....core.config import GEMINI_MODEL
from .tools import (
    read_specific_url,
    search_consumer_reviews,
    search_general_opinions,
    search_reddit_discussions,
    search_twitter_mentions,
)
from .prompt import OSINT_AGENT_PROMPT

osint_subagent = LlmAgent(
    name="osint_subagent",
    model=GEMINI_MODEL,
    instruction=OSINT_AGENT_PROMPT,
    description="Investigates ticketing URLs using social media, Reddit, Trustpilot, and web searches to detect fraud.",
    tools=[
        search_consumer_reviews,
        search_reddit_discussions,
        search_twitter_mentions,
        search_general_opinions,
        read_specific_url,
    ],
)

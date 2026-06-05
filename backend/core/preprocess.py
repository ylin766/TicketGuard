"""Preprocess agent: fetch the ticket page once, store it in session state.

The three feature agents (seat / price / security) all read the page from state
instead of fetching it themselves, so the network round-trip happens only once.
"""

import requests
from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext

from .config import GEMINI_MODEL, HTTP_TIMEOUT_SECONDS
from .prompt import PREPROCESS_INSTRUCTION
from .state_keys import PAGE_HTML, PAGE_URL

# Truncate very large pages so they fit comfortably in downstream prompts.
_MAX_HTML_CHARS = 200_000


def fetch_page(url: str, tool_context: ToolContext) -> dict:
    """Download a ticket-listing page and store its HTML in session state.

    Args:
        url: The full URL of the ticket listing page.
        tool_context: ADK-provided context used to write shared state.

    Returns:
        dict with keys: status, url, html_length (and error on failure).
    """
    try:
        response = requests.get(
            url,
            timeout=HTTP_TIMEOUT_SECONDS,
            headers={"User-Agent": "Mozilla/5.0 (TicketGuard)"},
        )
        response.raise_for_status()
        html = response.text[:_MAX_HTML_CHARS]

        tool_context.state[PAGE_URL] = url
        tool_context.state[PAGE_HTML] = html

        return {"status": "ok", "url": url, "html_length": len(html)}
    except requests.RequestException as exc:
        tool_context.state[PAGE_URL] = url
        tool_context.state[PAGE_HTML] = ""
        return {"status": "error", "url": url, "error": str(exc)}


preprocess_agent = LlmAgent(
    name="preprocess_agent",
    model=GEMINI_MODEL,
    instruction=PREPROCESS_INSTRUCTION,
    description="Fetches the ticket-listing page once and stores it in state.",
    tools=[fetch_page],
)

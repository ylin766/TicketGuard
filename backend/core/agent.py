"""Root orchestration chain.

    URL
     |
     v
  preprocess_agent          (fetch page once -> state)
     |
     v
  ParallelAgent             (feature agents, each writes *_result)
     |
     v
  results in state -> assembled into a report by server/core caller

There is no LLM "report agent": the final report is a mechanical merge of the
feature results, done by the API layer.

Currently only the ``security`` feature is implemented. Teammates add the
``seat`` and ``price`` feature agents back into ``features_parallel`` once their
sub-workflows exist.
"""

from google.adk.agents import ParallelAgent, SequentialAgent

from ..features.security import security_orchestrator
from .preprocess import preprocess_agent

# Feature agents run independently and concurrently.
# TODO: add seat_agent and price_agent here once implemented.
features_parallel = ParallelAgent(
    name="features_parallel",
    sub_agents=[security_orchestrator],
    description="Runs the implemented feature audits in parallel.",
)

# Global chain: fetch once, then fan out to the feature agents.
root_agent = SequentialAgent(
    name="ticket_guard",
    sub_agents=[preprocess_agent, features_parallel],
    description="Audits a ticket-listing URL across the implemented features.",
)

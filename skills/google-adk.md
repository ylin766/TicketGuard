# Google ADK (Agent Development Kit)

## Official Documentation

The authoritative source for all ADK patterns, APIs, and best practices:

- **LLM docs index**: https://adk.dev/llms.txt — use this to find the right page for any topic
- **Full LLM docs**: https://adk.dev/llms-full.txt — complete reference (fetch specific sections as needed)
- **Python SDK source**: https://github.com/google/adk-python
- **Official samples** (4.1k ⭐): https://github.com/google/adk-samples
- **ADK coding with AI guide**: https://adk.dev/tutorials/coding-with-ai/

When writing ADK code, always fetch the relevant page from `adk.dev` to get the latest API signatures before writing any code.

## Key Documentation Pages

| Topic | URL |
|---|---|
| Quickstart (Python) | https://adk.dev/get-started/python/index.md |
| Simple agents (LlmAgent) | https://adk.dev/agents/llm-agents/index.md |
| Custom function tools | https://adk.dev/tools-custom/function-tools/index.md |
| MCP tools | https://adk.dev/tools-custom/mcp-tools/index.md |
| BigQuery built-in tool | https://adk.dev/integrations/bigquery/index.md |
| Computer Use (browser) | https://adk.dev/integrations/computer-use/index.md |
| Sequential workflow | https://adk.dev/agents/workflow-agents/sequential-agents/index.md |
| Multi-agent (sub_agents) | https://adk.dev/tutorials/agent-team/index.md |
| Session & state | https://adk.dev/sessions/index.md |
| Deploy to Cloud Run | https://adk.dev/deploy/cloud-run/index.md |

## Key Sample Agents to Reference

| Sample | Relevant patterns | URL |
|---|---|---|
| `software-bug-assistant` | MCP (stdio + HTTP), AgentTool, LangChain tool | https://github.com/google/adk-samples/tree/main/python/agents/software-bug-assistant |
| `brand-search-optimization` | Selenium browser control, screenshot + Gemini Vision, multi-agent | https://github.com/google/adk-samples/tree/main/python/agents/brand-search-optimization |
| `data-science` | BigQuery built-in tool, MCP Toolbox for Databases | https://github.com/google/adk-samples/tree/main/python/agents/data-science |
| `deep-search` | Multi-step workflow, web search, Human-in-the-Loop | https://github.com/google/adk-samples/tree/main/python/agents/deep-search |

## Installation

```bash
pip install google-adk
pip install "google-adk[extensions]"  # includes MCP, LangChain, etc.
```

Requirements: Python 3.11+

## Run Locally

```bash
adk run ticket_guard      # CLI mode
adk web                   # Web UI at http://localhost:8000
```

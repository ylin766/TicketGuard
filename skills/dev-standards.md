# TicketGuard Development Standards

## References

- **Google Engineering Practices**: https://github.com/google/eng-practices
- **Google Python Style Guide**: https://google.github.io/styleguide/pyguide.html
- **Conventional Commits spec**: https://www.conventionalcommits.org/en/v1.0.0/
- **Google styleguide (all languages)**: https://github.com/google/styleguide

---

## Git Workflow

### Branch Strategy

Always branch off `main`. Never commit directly to `main`.

```
main                    ← protected, always deployable
├── feat/domain-check   ← new feature
├── feat/fivetran-mcp   ← new feature
├── fix/ssl-timeout     ← bug fix
└── chore/update-deps   ← maintenance
```

```bash
# Start new work
git checkout main
git pull origin main
git checkout -b feat/your-feature-name

# Push and open PR
git push -u origin feat/your-feature-name
# Then open PR on GitHub: https://github.com/ylin766/TicketGuard
```

Branch naming: `feat/`, `fix/`, `chore/`, `refactor/`, `docs/` + short kebab-case description.

### Pull Request Rules

- PR title follows the same Conventional Commits format as commit messages
- Every PR must target `main`
- At least one teammate review before merge
- Squash merge preferred to keep `main` history clean
- Delete branch after merge

---

## Commit Message Format

Follow **Conventional Commits**: `type(scope): description`

```
type(scope): short description

Optional longer body explaining WHY, not WHAT.
```

### Types

| Type | When to use |
|---|---|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `refactor` | Code restructure without behavior change |
| `chore` | Dependency updates, config, tooling |
| `docs` | Documentation only |
| `test` | Adding or fixing tests |
| `perf` | Performance improvement |

### Scopes (TicketGuard-specific)

| Scope | What it covers |
|---|---|
| `agent` | Root agent, orchestration logic |
| `tools` | Any tool function (domain_check, bigquery, etc.) |
| `fivetran` | Fivetran MCP integration or Connector SDK |
| `browser` | Selenium / browser control tools |
| `pipeline` | Data pipeline definitions |
| `readme` / `docs` | Documentation files |
| `deps` | Dependency changes |

### Examples

```
feat(tools): add domain similarity check against official whitelist
fix(browser): handle selenium timeout when page load exceeds 10s
refactor(agent): extract seat extraction into dedicated sub-agent
chore(deps): upgrade google-adk to 2.0.1
docs(readme): add tech stack badges
feat(fivetran): add SeatGeek custom connector for market listings
```

---

## Python Code Standards

Follow **Google Python Style Guide**: https://google.github.io/styleguide/pyguide.html

### Key Rules

**Naming**
```python
# Modules and packages: snake_case
domain_check.py
fivetran_mcp.py

# Functions and variables: snake_case
def check_domain(url: str) -> dict:
listing_price_usd = 3200.0

# Classes: PascalCase
class TicketGuardAgent:

# Constants: UPPER_SNAKE_CASE
MAX_TIMEOUT_SECONDS = 15
OFFICIAL_DOMAINS = ["stubhub.com", "ticketmaster.com"]
```

**Type annotations — always required**
```python
# Good
def query_market_prices(match_id: str, section: str) -> dict:

# Bad
def query_market_prices(match_id, section):
```

**Docstrings — required for all public functions**
```python
def domain_check_tool(url: str) -> dict:
    """
    Check if a URL's domain is suspicious.

    Args:
        url: The full URL of the ticket listing page.

    Returns:
        dict with keys: credibility_score, is_suspicious, flags
    """
```

**Error handling — never let exceptions propagate silently**
```python
# Good
try:
    result = external_api_call()
except requests.Timeout:
    return {"error": "API timeout", "score": 0}
except Exception as e:
    logging.error("Unexpected error in domain_check: %s", e)
    return {"error": str(e), "score": 0}

# Bad
result = external_api_call()  # crashes the agent if this fails
```

**No magic numbers**
```python
# Good
DOMAIN_AGE_RISK_THRESHOLD_DAYS = 30
SIMILARITY_SUSPICIOUS_THRESHOLD = 0.7

if domain_age_days < DOMAIN_AGE_RISK_THRESHOLD_DAYS:
    flags.append("NEW_DOMAIN")

# Bad
if domain_age_days < 30:
    flags.append("NEW_DOMAIN")
```

---

## Design Principles

### Don't Repeat Yourself (DRY)

Extract shared logic into `shared_libraries/` or `tools/`. If the same code appears in two places, it belongs in a shared module.

```
ticket_guard/
├── shared_libraries/
│   ├── bigquery_client.py   ← single BigQuery client, used by all tools
│   ├── constants.py         ← OFFICIAL_DOMAINS, timeouts, thresholds
│   └── http_client.py       ← shared requests session with retry logic
```

### Single Responsibility

Each tool does exactly one thing. If a function name has "and" in it, split it.

```python
# Bad
def check_domain_and_take_screenshot(url): ...

# Good
def check_domain(url): ...
def take_screenshot(tool_context): ...
```

### Fail Gracefully, Always

Every tool must return a valid dict even on failure. The agent must always be able to produce a report, even if some steps fail.

```python
# Every tool follows this pattern
def my_tool(input: str) -> dict:
    try:
        # ... implementation
        return {"status": "ok", "result": ...}
    except Exception as e:
        return {"status": "error", "error": str(e), "result": None}
```

### Lazy Initialization for External Clients

Never initialize external clients (Selenium, BigQuery, HTTP sessions) at import time. Use module-level state dicts.

```python
# Good — lazy init
_state = {"driver": None, "bq_client": None}

def _get_driver():
    if _state["driver"] is None:
        _state["driver"] = webdriver.Chrome(options=_get_options())
    return _state["driver"]

# Bad — crashes at import if Chrome not available
driver = webdriver.Chrome()
```

### Use Environment Variables, Never Hardcode Secrets

```python
# Good
api_key = os.environ["FIVETRAN_API_KEY"]

# Bad
api_key = "abc123xyz"
```

---

## File Organization

```
ticket_guard/
├── __init__.py              ← exports root_agent only
├── agent.py                 ← root_agent definition
├── prompt.py                ← all prompt strings
├── shared_libraries/
│   ├── constants.py         ← shared constants
│   └── bigquery_client.py   ← shared BQ client
├── tools/
│   ├── domain_check.py      ← one file per tool
│   ├── regulation_lookup.py
│   └── browser_tools.py
└── sub_agents/
    ├── website_auditor/
    │   ├── agent.py
    │   └── prompt.py
    └── report_agent/
        ├── agent.py
        └── prompt.py
```

One tool per file. One agent per file. Prompts always in `prompt.py`, never inline in `agent.py`.

# Browser Security Check for Ticket Links

Layer 2 (visual) of the TicketGuard security feature. Given a ticket-selling URL,
it opens the page in a controlled [browser-use](https://github.com/browser-use/browser-use)
session, captures the real page (final URL, title, screenshot, body text,
clickable elements), safely probes **up to two** purchase-flow transitions,
detects sensitive ticket actions, and returns a **rule-based** risk verdict with
evidence.

It does **not** decide scam from a login/payment page alone. Login/payment is a
sensitive *decision point*. Risk rises only when a sensitive action co-occurs
with an unverified or inconsistent context: brand/domain mismatch, off-platform
payment (Zelle/Venmo/Cash App/crypto/gift card), OTP/transfer-code requests,
suspicious redirects, or an event mismatch.

## Layout

| Path | Responsibility |
|------|----------------|
| `browser_security_tool.py` | The async ADK FunctionTool entry point |
| `browser_runner.py` | The guard-railed ReAct agent that drives `BrowserSession` |
| `schemas.py` | Pydantic models — the stable output contract |
| `llm/prompts.py` | Gemini prompts: claim / sensitive-action extraction + the ReAct browse instruction |
| `llm/gemini_client.py` | Gemini JSON+vision helper (lazy client) |
| `rules/domain_rules.py` | Deterministic trust check + risk scoring (the verdict) |
| `osint/osint_escalation.py` | Reputation OSINT escalation for non-whitelisted sites |
| `tests/` | Offline unit tests (no browser / LLM) |
| `test_runs/<site>/` | Saved demo outputs (one folder per tested site) |

A native ADK `LlmAgent` explores the page by calling `click_element` / `go_back`
/ `finish` tools (guard rails enforced inside the tools); the LLM only
**describes / explores**, and the **verdict** is made by deterministic
`rules/domain_rules` so it stays auditable. Unfamiliar (non-whitelisted) sites
are additionally reputation-checked via `osint/`.

## Install

From `backend/` (Python ≥ 3.11):

```bash
pip install -e '.[browser-security]'
browser-use install            # downloads Chromium (one-time)
export GOOGLE_API_KEY=...       # or set GEMINI_MODEL to override the model
```

## Use (as a tool)

```python
import asyncio
from features.security.agent.browser_check.browser_security_tool import (
    browser_security_check,
)

result = asyncio.run(browser_security_check(
    "https://www.ticketmaster.com/event/...",
    expected_event="World Cup Final",   # optional cross-checks
    expected_venue="MetLife Stadium",
))
print(result["risk_level"], result["verdict"])
```

## Use (as an ADK agent)

`features.security.agent.browser_security_agent` is a Gemini `LlmAgent` with this
tool attached, ready to drop into the security workflow.

## Output

A `BrowserSecurityResult` dict: `risk_level` (low/medium/high/unknown),
`risk_score` (0-100), `verdict`, `summary`, `claim`, `sensitive_action`,
`trust_check`, `transitions`, `evidence`, `recommended_action`, `snapshots`.

## Risk model (summary)

Strong flags (additive): off-platform payment (+45), brand/domain mismatch (+35),
sensitive action on untrusted domain (+30), OTP/transfer-code (+25), private
seller payment (+25), suspicious redirect (+20), event mismatch (+20), login on
untrusted domain (+15). Benign deductions: trusted+matching platform (−25),
in-platform payment (−15), event match (−10), listing-only (−10). Clamped 0-100;
**≥60 high, 30-59 medium, <30 low**. A captcha/error page is never reported safe.

## Safety

The module **never** enters personal info, credentials, OTP, transfer codes, or
card details, and **never** clicks Pay / Place Order / Confirm / Accept Transfer /
Submit Code / Send Payment / Connect Wallet (enforced by a label guard before
every click), with a hard depth cap of 2.

## Tests

```bash
cd backend && python -m pytest features/security/agent/browser_check/tests/ -q
```

The tests exercise the deterministic decision layer with mocked observations
(no browser/Gemini needed), covering: legit listing, quantity modal, in-platform
payment, brand/domain mismatch, off-platform payment, captcha, redirect
detection, risk banding, and JSON parsing.

## Manual browser debugging

```bash
browser-use --version
# drive a real (headed) browser to eyeball a page:
python -c "import asyncio; from browser_use import BrowserSession; \
  s=BrowserSession(headless=False); \
  asyncio.run((lambda: (s.start(), s.navigate('https://example.com')))())"
```

# Browser Security Check — Live Test Log

Real end-to-end runs of `browser_security_check` (headless Chromium + Gemini
vision + deterministic scoring). Model: `gemini-2.5-flash`.

---

## Run 1 — Eventbrite homepage (legit baseline)

- **Date:** 2026-06-07
- **URL:** `https://www.eventbrite.com/`
- **Verdict:** `likely_safe_browser_context` — risk_level **low**, score **0**
- **Claim:** platform=Eventbrite, page_state=event_listing
- **Sensitive action:** none
- **Trust:** trusted=True, brand/domain match=True, off-platform=False
- **Transitions:** step 0 → no safe purchase-flow click (homepage links lead to
  category lists, not a specific ticket flow) → correctly stopped.
- **Errors:** none

Demonstrates the legit path: trusted domain + matching brand + no sensitive
action → low risk, and the transition ranker correctly declines to wander.

---

## Run 2 — StubHub, World Cup Atlanta (legit, deep probe)

- **Date:** 2026-06-07
- **URL:** `https://www.stubhub.com/world-cup-atlanta-tickets-6-21-2026/event/153022910/?quantity=1&adattrib=...`
- **Inputs:** expected_event="World Cup", expected_venue="Atlanta", max_click_depth=2
- **Verdict:** `likely_safe_browser_context` — risk_level **low**, score **0**
- **Claim (Gemini-extracted from the real page):**
  - platform = **StubHub**
  - event = **Spain vs Saudi Arabia - World Cup - Group H (Match 38)**
  - venue = **Mercedes-Benz Stadium**
  - date = **June 21, 2026, 12:00 PM**
- **Sensitive action:** none (payment_context=none)
- **Trust:** trusted=True, brand/domain match=True, off-platform=False,
  suspicious_redirect=False, **event_mismatch=False** (matched expected inputs)
- **Transitions:**
  - step 0: clicked **"Continue"** on the "How many tickets?" quantity modal
  - step 1: no safe element to go deeper (seat-map price cards are not exposed as
    clickable DOM elements) → correctly stopped
- **Errors:** none
- **Artifacts:** `stubhub_step_0.png`, `stubhub_step_1.png`, `stubhub_result.json`

### Screenshots
- `stubhub_step_0.png` — Mercedes-Benz Stadium seat map + "How many tickets?"
  modal (1 ticket selected, Continue button).
- `stubhub_step_1.png` — after Continue: full seat map with 124 listings.

---

## Issues found & fixed during these runs

1. **White/blank screenshot on JS SPA pages.** First StubHub run captured a blank
   page — `navigate()` returns ~0.5s in, long before the React SPA paints.
   **Fix:** added `_settle()` (wait for `domcontentloaded` + `networkidle` with a
   12s cap, a scroll nudge, and a 5s grace period) before every capture.
   Re-run produced fully rendered screenshots.

2. **Gemini 503 "model is overloaded" aborted the run.** A transient server-side
   spike raised `ServerError 503` and ended the check as
   `unknown_browser_check_failed`. **Fix:** added retry-with-backoff (2s/5s/10s,
   up to 3 attempts) on transient statuses (429/500/502/503/504) in
   `gemini_client._gemini_json`. Re-run auto-recovered from two 503s.

Both fixes confirmed working in Run 2.

---

## Not yet tested live

- A genuine **high-risk** scam page (brand/domain mismatch, off-platform payment,
  transfer-code request). These are covered by unit tests with mocked LLM output
  (`tests/test_domain_rules.py`, cases 4 & 5) but not yet by a live URL — supply
  a real suspicious link to validate the high-risk path end-to-end.

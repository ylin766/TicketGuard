"""The three Gemini prompts used by the browser security check.

Each prompt is JSON-only and describe-don't-decide: the models extract structure
(claim / sensitive action / safe next click); the scam verdict is made later by
the deterministic rules in ``domain_rules``.
"""

# --------------------------------------------------------------------------- #
# Prompt 1: Claim Extraction                                                  #
# --------------------------------------------------------------------------- #

CLAIM_EXTRACTION_PROMPT = """\
You are analyzing a ticket-selling webpage for a browser security check.

Your task is ONLY to extract what the page claims. Do not decide whether it is a scam.
Use the screenshot (if provided), current URL, page title, visible text, and clickable elements.

Important rules:
- First decide is_ticket_site: true if this page belongs to a site that sells or
  resells EVENT TICKETS (concerts, sports, theater, festivals). Set it false for
  unrelated sites — gambling/casino/sportsbook, news, social media, generic
  e-commerce, a search engine, a parked/blank/for-sale domain, etc. If the page
  is a captcha/bot-check/error and you cannot tell, leave is_ticket_site true.
- Identify the primary ticket platform or marketplace shown by the page, such as Ticketmaster, AXS, SeatGeek, StubHub, TickPick, Vivid Seats, GameTime, Eventbrite, FIFA, a venue official site, or unknown.
- Do not confuse payment partners or ads with the main platform. PayPal shown as a payment option is not the ticketing platform.
- Extract event name, venue, city/state, date/time, and visible price range if present.
- Classify the current page state.
- Quantity selection modals like "How many tickets?" are normal ticket-flow pages, not payment pages.
- Scarcity labels like "Only 3% left", "Last ticket", "Best Deal", "Hidden gem", "Amazing", "Budget Deal" are common marketplace UI labels and should not by themselves imply scam.

Allowed page_state values:
- event_listing: event page with seat map, listing cards, sections, prices
- quantity_modal: asks how many tickets, quantity selector, ticket count modal
- ticket_detail: selected ticket detail / cart preview but no login/payment form yet
- login_required: asks user to sign in or enter email/password
- payment_required: asks for card, billing, PayPal checkout, or platform payment
- ticket_transfer_claim: asks user to accept/claim transferred tickets
- off_platform_payment: asks user to pay via Zelle/Venmo/Cash App/crypto/gift card/wire/private chat
- blocked_or_captcha: captcha, bot check, access denied, waiting room
- error_page: broken page, 404, unavailable
- unknown: cannot determine

If the caller provided an expected event/venue/date, they are given below only for
your awareness; still report what the PAGE itself claims.
EXPECTED_EVENT: {expected_event}
EXPECTED_VENUE: {expected_venue}
EXPECTED_DATE: {expected_date}

Return JSON only, matching this schema:
{{
  "claimed_platform": string|null,
  "claimed_domain": string|null,
  "is_ticket_site": boolean,
  "marketplace_type": "primary"|"resale"|"venue"|"social"|"unknown",
  "claimed_event": string|null,
  "claimed_venue": string|null,
  "claimed_city_state": string|null,
  "claimed_date_time": string|null,
  "visible_price_range": string|null,
  "page_state": "event_listing"|"quantity_modal"|"ticket_detail"|"login_required"|"payment_required"|"ticket_transfer_claim"|"off_platform_payment"|"blocked_or_captcha"|"error_page"|"unknown",
  "confidence": "high"|"medium"|"low",
  "evidence": [string]
}}

Input context:
CURRENT_URL: {url}
REGISTERED_DOMAIN: {registered_domain}
PAGE_TITLE: {title}
VISIBLE_TEXT:
{text}

CLICKABLE_ELEMENTS:
{clickables}
"""


# --------------------------------------------------------------------------- #
# Prompt 2: Sensitive Ticket Action Detection                                 #
# --------------------------------------------------------------------------- #

SENSITIVE_ACTION_PROMPT = """\
You are analyzing a ticket-selling webpage for sensitive ticket-related actions.

Sensitive ticket actions include:
- sign in / login
- entering email, username, password
- entering OTP, verification code, SMS code, or ticket transfer code
- entering card number, billing address, or payment information
- PayPal / wallet checkout inside a known platform
- accepting or claiming transferred tickets
- connecting a wallet
- downloading an app to continue
- paying outside the platform via Zelle, Venmo, Cash App, crypto, gift card, wire transfer
- messaging a seller to pay privately

Important rules:
- A sensitive action is NOT automatically a scam. It only means stronger trust verification is needed.
- A normal event listing, seat map, price list, ticket quantity modal, or filter panel is not sensitive.
- PayPal or credit card inside Ticketmaster/SeatGeek/StubHub/TickPick/AXS checkout can be normal inside-platform payment.
- Off-platform payment requests are high-risk evidence: Zelle, Venmo, Cash App, crypto, gift cards, wire transfer, WhatsApp/Telegram/Instagram DM seller payment.
- Do not mark scarcity / marketing labels as sensitive actions.
- Stop before any irreversible action: Pay, Place Order, Confirm Purchase, Accept Transfer, Submit Code, Send Payment.

Return JSON only:
{{
  "is_sensitive_action_page": boolean,
  "page_state": "event_listing"|"quantity_modal"|"ticket_detail"|"login_required"|"payment_required"|"ticket_transfer_claim"|"off_platform_payment"|"blocked_or_captcha"|"error_page"|"unknown",
  "action_types": ["login"|"password"|"otp_or_verification_code"|"payment"|"billing_info"|"ticket_transfer"|"ticket_transfer_code"|"wallet_connect"|"off_platform_payment"|"private_message_seller"|"download_app"|"none"],
  "payment_context": "inside_platform"|"off_platform"|"unknown"|"none",
  "payment_methods": [string],
  "requested_inputs": [string],
  "irreversible_action_visible": boolean,
  "evidence": [string]
}}

Input context:
CURRENT_URL: {url}
REGISTERED_DOMAIN: {registered_domain}
PAGE_TITLE: {title}
CLAIM_EXTRACTION_JSON:
{claim_json}
VISIBLE_TEXT:
{text}

CLICKABLE_ELEMENTS:
{clickables}
"""


# --------------------------------------------------------------------------- #
# ReAct Browse Agent instruction (native ADK LlmAgent + tools)                #
# --------------------------------------------------------------------------- #

BROWSE_REACT_INSTRUCTION = """\
You are an autonomous, OBSERVE-ONLY security explorer inspecting a ticket-selling
website inside a real browser. Your job is to MAP every SENSITIVE surface the site
leads to and observe what each one demands — login (does it ask for email /
password?), payment (card / PayPal / off-platform Zelle-Venmo-crypto?), ticket
transfer, OTP / transfer code — so a downstream rules engine can judge scam risk.
You explore and describe; you never decide the verdict and never buy or submit.

You drive the browser by calling these tools, ONE per turn:
- click_element(index, reason): click a candidate index to go deeper — INCLUDING
  clicking "Sign in" / "Checkout" / "Claim" to step ONTO a sensitive page and see
  what it requires. Also use it to dismiss blocking modals ("Accept & Continue").
- go_back(reason): return to the previous page to explore a DIFFERENT branch —
  use this right after you've observed a sensitive page.
- finish(summary): stop once you've reached the sensitive surfaces you can, or no
  useful unexplored branch remains. Then reply with a one-line summary.

Each tool returns the new page: its URL, page_state, whether it's a sensitive
decision point, and the indexed list of safe clickable candidates. Use that to
choose your next move.

Strategy — thorough and breadth-first:
1. From the listing, follow a promising path inward (a price/section card, "Buy/Get
   Tickets", "Continue", "Checkout", "Sign in", "Claim/Accept tickets"; smallest
   quantity, usually 1).
2. When you land ON a real sensitive page you've recorded what it asks for — do NOT
   type or submit. go_back and probe a DIFFERENT branch (saw login? go check
   checkout; saw checkout? check transfer / contact-seller).
3. Don't re-click links you've already followed; pick a different element each time.
   A go_back may re-show a dismissable modal — dismiss it once, then go somewhere new.

Hard rules (the tools also enforce these — reaching a page is fine, acting is not):
- NEVER click Pay, Place Order, Confirm Purchase, Submit Payment, Accept Transfer,
  Submit Code, Send Payment, Connect Wallet, or anything irreversible.
- NEVER enter or submit credentials, OTP, transfer codes, or payment details.
- Avoid noise: favorite, share, filters, sort, currency, language, search, map zoom,
  chat bot, help, terms, cookie settings, carousel controls.
- Respect tool feedback: if a tool says an action was refused or you're on a
  sensitive page, adapt — pick another candidate, go_back, or finish.

Stop and call finish when login AND checkout/payment (and any transfer/contact path)
have been observed, or the action budget shown in actions_used is nearly spent.
"""


# --------------------------------------------------------------------------- #
# Prompt 3b: Browse Agent (legacy structured-decision loop)                   #
# --------------------------------------------------------------------------- #

BROWSE_AGENT_PROMPT = """\
You are an autonomous, OBSERVE-ONLY security explorer inspecting a ticket-selling
website. Your goal is to MAP every SENSITIVE surface the site leads to and
OBSERVE what each one demands — login (does it ask for email/password?), payment
(card? PayPal? off-platform Zelle/Venmo/crypto?), ticket-transfer claim, OTP /
transfer code — so a downstream rules engine can judge scam risk. You explore and
describe; you never decide the verdict, and you never buy or submit anything.

You choose ONE action each step:
- "click": advance by clicking a candidate element index — INCLUDING clicking
  "Sign in" / "Checkout" / "Claim" to step ONTO a sensitive page so you can see
  what it requires. Dismiss blocking modals (e.g. "Accept & Continue") this way.
- "go_back": return to the previous page to explore a DIFFERENT branch — use this
  right AFTER you have observed a sensitive page, to go find OTHER ones.
- "finish": stop, because you have reached and observed the sensitive surfaces you
  can, or no useful unexplored branch remains.

Strategy — be thorough and breadth-first:
1. From the main listing, follow a promising path inward ("Buy/Get Tickets", a
   price/section card, "Continue", "Checkout", "Sign in", "Claim/Accept tickets",
   "Contact seller"; smallest quantity, usually 1, in a quantity modal).
2. When you land ON a real sensitive page, you've recorded what it asks for —
   do NOT type or submit anything there. go_back and try a DIFFERENT branch to
   surface more sensitive pages (e.g. after seeing login, go back and probe
   checkout; after checkout, probe transfer/contact-seller).
3. Keep probing NEW branches until you've covered the obvious sensitive paths
   (login AND checkout/payment AND, if present, transfer / contact-seller). Don't
   re-follow links you've already taken (see VISITED and HISTORY) — pick a
   different element each time. A go_back may reload the page and re-show a
   dismissable modal (e.g. "Accept & Continue"); dismiss it once, then go to a
   branch you haven't explored yet. Finish only when no new sensitive branch
   remains.

Hard safety rules (the runner also enforces these — reaching a page is fine,
acting on it is not):
- NEVER click Pay, Place Order, Confirm Purchase, Submit Payment, Accept Transfer,
  Submit Code, Send Payment, Connect Wallet, or anything irreversible.
- NEVER enter or submit credentials, OTP, transfer codes, or payment details.
- Avoid noise: heart/favorite, share, filters, sort, currency, language, search,
  map zoom, chat bot, help, terms, cookie settings, carousel controls.

If the current page IS a sensitive decision point (login/payment/transfer/
off-platform) or cannot be inspected (captcha/error), you have already observed
it — only "go_back" or "finish" are valid now.

Return JSON only:
{{
  "action": "click"|"go_back"|"finish",
  "target_index": integer|null,
  "action_label": string|null,
  "reason": string,
  "safety": "safe"|"unsafe"|"uncertain"
}}

Input context:
CURRENT_URL: {url}
PAGE_STATE: {page_state}
CURRENT_PAGE_IS_SENSITIVE_OR_BLOCKED: {restricted}
ACTIONS_REMAINING: {budget_left}
CLAIM_EXTRACTION_JSON:
{claim_json}
SENSITIVE_ACTION_JSON:
{sensitive_json}

SENSITIVE_SURFACES_FOUND_SO_FAR:
{surfaces}

VISITED_URLS:
{visited}

HISTORY (most recent last):
{history}

CLICKABLE_ELEMENTS:
{clickables}
"""


# --------------------------------------------------------------------------- #
# Prompt 3: Transition Ranking (legacy — superseded by BROWSE_AGENT_PROMPT)    #
# --------------------------------------------------------------------------- #

TRANSITION_RANKING_PROMPT = """\
You are helping safely inspect a ticket-selling webpage.

The page is not currently a sensitive-action page. Choose at most ONE clickable
element index that is most likely to move the user one step deeper into the
ticket purchase flow, so the security checker can observe whether
login/payment/transfer/off-platform payment appears.

Preferred safe clicks by page state:
- event_listing: ticket listing card, price card, section card, "Buy Tickets", "Get Tickets", "Select", first/lowest visible listing
- quantity_modal: choose the smallest concrete ticket quantity available, usually 1; if 1 unavailable choose 2; avoid "Any" unless it is the only choice
- ticket_detail: "Continue" or "Checkout" only if it does not say Pay / Place Order / Confirm Purchase

Avoid these elements:
- heart/favorite, share, filters, sort, currency, language, search bar, map zoom +/-, chat bot, help, terms, cookie settings, carousel controls
- header "Sign In" unless the page itself requires sign-in to continue
- Pay, Place Order, Confirm Purchase, Submit Payment, Accept Transfer, Submit Code, Transfer Now, Send Payment
- Any element that would enter or submit personal information, credentials, OTP, transfer code, or payment details

Safety rules:
- Never choose an index for an irreversible action.
- Never choose a click that submits payment, accepts transfer, or submits a verification code.
- If no safe purchase-flow click exists, return should_click=false.

Return JSON only:
{{
  "should_click": boolean,
  "chosen_index": integer|null,
  "action_label": string|null,
  "reason": string,
  "safety": "safe"|"unsafe"|"uncertain"
}}

Input context:
CURRENT_URL: {url}
PAGE_STATE: {page_state}
CLAIM_EXTRACTION_JSON:
{claim_json}
SENSITIVE_ACTION_JSON:
{sensitive_json}

CLICKABLE_ELEMENTS:
{clickables}
"""

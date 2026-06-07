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
# Prompt 3: Transition Ranking                                                #
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

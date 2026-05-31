# 🎫 TicketGuard

> **Your real-time gatekeeper before you click "Buy"** — a multi-step AI Agent that audits any ticket listing URL for fraud, obstructed views, price manipulation, and legal violations before you spend thousands on a FIFA 2026 World Cup ticket.

📖 [查看中文文档 (Chinese Documentation)](./README.zh.md)

---

## The Problem

FIFA 2026 World Cup tickets are the most expensive in history — Final tickets exceed **$2,000 face value** and scalpers are asking **$8,000+** on secondary markets. Fraud is rampant, and buyers have **no tool to verify a listing before clicking Buy**.

Three core fraud types target buyers:

| Fraud Type | Method | Buyer Pain |
|---|---|---|
| **Fake Ticketing Sites** | Clone StubHub/Ticketmaster pages with tweaked domains (e.g. `stubhub-tickets.com`) | Visually identical to real sites — impossible to spot without tools |
| **Obstructed View Fraud** | Sell seats blocked by structural columns or broadcast cameras as normal tickets | Warnings are buried; buyers can't see the real view before purchase |
| **Illegal Price Gouging** | Exploit information gaps to charge far above legal resale caps (NY state caps at 10% over face value) | Buyers don't know local anti-scalping laws |

---

## What TicketGuard Does

Paste any ticket listing URL into TicketGuard. In ~30 seconds, the Agent autonomously runs a **6-step analysis chain** and outputs a risk scorecard with a clear buy/don't-buy recommendation.

```
User pastes a ticket listing URL
        │
        ▼
Agent visits the page (Browser-Use sandbox)
Runs 6-step analysis chain (~30 seconds)
        │
        ▼
Outputs: Risk Scorecard + Purchase Recommendation
User decides whether to proceed
```

---

## Agent Workflow (Multi-Step Mission)

### Step 1 — Website Credibility Audit
- Browser-Use sandbox visits the URL and captures screenshot + HTML
- **DomainCheck Tool**: fuzzy-matches target domain against official whitelist; flags domains registered < 30 days ago via WHOIS; validates SSL certificate
- **Gemini Vision**: analyzes screenshot for visual impersonation of official platforms; detects off-platform payment prompts (WeChat, Venmo, Zelle)
- Outputs: **Website Credibility Score (0–100)**

### Step 2 — Seat Information Extraction
- Gemini parses page content to extract structured JSON: venue, section, row, seat, listing price
- Matches venue name against the 16 official FIFA 2026 stadiums

### Step 3 — Sightline Audit
- **Browser-Use** navigates to [A View From My Seat](https://aviewfrommyseat.com) for the target section
- **Gemini Vision** analyzes crowdsourced seat photos: identifies obstructions (columns, broadcast cameras, railings)
- Flags World Cup-specific risk: broadcast camera positions are fixed per match
- Outputs: **Sightline Score (0–100)**

### Step 4 — Real-Time Market Price Comparison
- **Fivetran MCP** triggers Pipeline_Market → syncs SeatGeek live listings to BigQuery
- Queries P25/P50/P75 price distribution for same match + section
- Detects duplicate listings (same seat number, multiple sellers → fraud signal)
- Adjusts benchmark by match stage (Group Stage vs. Knockout vs. Final)
- Outputs: **Price Score (0–100)**

### Step 5 — Legal Compliance Check
- **Fivetran MCP** triggers Pipeline_Regulation → syncs official face values + resale caps to BigQuery
- Identifies venue's state/province and applicable anti-scalping law
- Calculates actual markup vs. legal cap (e.g. NY: 10% cap, CO: no cap)
- Outputs: **Compliance Score (0–100)**

### Step 6 — Comprehensive Report
- Aggregates all 5 dimension scores with weighted formula:
  - Website Credibility: 40% · Price: 25% · Compliance: 20% · Sightline: 15%
- Outputs final **Risk Scorecard** with purchase recommendation

---

## Sample Output

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎫 TicketGuard Pre-Purchase Report
Page:  stubhub-tickets.com/listing/98234
Match: USA vs Mexico | MetLife Stadium | Section 114A Row 3 Seat 7
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 Website Credibility:  12/100  🚫 Likely Counterfeit
   Domain registered: 3 days ago | Official domain: stubhub.com
   Off-platform payment detected: page requests Venmo payment

📍 Seat Extracted:  Section 114A / Row 3 / Seat 7
   Listing Price: $3,200

👁️ Sightline Score:  71/100  ✅ Generally Clear
   No fixed obstructions detected, left-goal angle 92%
   (Note: if site is counterfeit, seat info itself is unverifiable)

💰 Price Score:  28/100  ⚠️ Severe Markup
   Market median: $1,450 (SeatGeek live P50)
   Markup: +120%, exceeds NY legal cap by 310%

⚖️ Compliance Score:  0/100  🚫 Potentially Illegal
   NY Anti-Scalping Law Art. 25-AA caps resale at ≤10% over face value

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Recommendation: ❌ Strongly advise against purchase
                (Counterfeit site + illegal markup)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## FIFA 2026 World Cup Differentiators

Generic phishing detection tools only check site authenticity. TicketGuard adds three World Cup-specific layers:

**1. Sightline Intelligence via Crowdsourced Photos**
Real seat-view photos from [A View From My Seat](https://aviewfrommyseat.com), analyzed by Gemini Vision in real time. Flags broadcast camera obstructions — a World Cup-specific risk since camera positions are fixed per match.

**2. Three-Country Legal Compliance Engine**
- US: state-by-state anti-scalping laws (NY 10% cap, CO no cap, etc.)
- Canada: provincial ticket resale regulations
- Mexico: Federal Consumer Protection Law (PROFECO)
Agent auto-matches venue location to applicable law and gives a clear legal verdict.

**3. Match-Stage-Aware Price Benchmarking**
Price comparison accounts for match importance — Group Stage, Knockout, and Final tickets have completely different fair-value baselines. Powered by wc26-mcp match schedule data.

---

## Tech Stack

![Google ADK](https://img.shields.io/badge/Google_ADK-4285F4?style=for-the-badge&logo=google&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini_2.5-8E75B2?style=for-the-badge&logo=google&logoColor=white)
![Fivetran](https://img.shields.io/badge/Fivetran_MCP-00A1E0?style=for-the-badge&logo=fivetran&logoColor=white)
![BigQuery](https://img.shields.io/badge/BigQuery-4285F4?style=for-the-badge&logo=googlebigquery&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Selenium](https://img.shields.io/badge/Selenium-43B02A?style=for-the-badge&logo=selenium&logoColor=white)
![SeatGeek](https://img.shields.io/badge/SeatGeek_API-FA5252?style=for-the-badge&logoColor=white)

| Layer | Technology | Role |
|---|---|---|
| **Agent Framework** | [Google ADK](https://adk.dev/) | Orchestrates 6-step workflow and tool call sequence |
| **Core Model** | Gemini 2.5 Flash (multimodal) | Screenshot analysis, visual fraud detection, sightline report generation |
| **Partner MCP** | [Fivetran MCP Server](https://github.com/fivetran/fivetran-mcp) | Triggers 3 data pipelines on demand, syncs to BigQuery |
| **Data Pipelines** | Fivetran Connector SDK | Custom connectors for SeatGeek API and PhishHunt feed |
| **Browser Control** | Selenium + ADK Computer Use | Sandbox access to ticket pages + A View From My Seat |
| **Data Warehouse** | Google BigQuery | Stores market listings, regulation reference, phishing domain intelligence |
| **Match Data** | [wc26-mcp](https://github.com/jordanlyall/wc26-mcp) | FIFA 2026 match schedule, venues, and team data via MCP |
| **Market Prices** | [SeatGeek API](https://seatgeek.github.io/) | Real-time secondary market ticket listings |
| **Tool 1** | DomainCheck Tool | Domain similarity + WHOIS + SSL detection |
| **Tool 2** | RegulationLookup Tool | Queries anti-scalping law resale caps by venue location |

---

## Fivetran Data Pipelines (Partner Power)

Fivetran MCP Server drives three on-demand data pipelines — no manual ETL required:

| Pipeline | Source | Destination | Trigger |
|---|---|---|---|
| **Pipeline_Market** | SeatGeek API (live listings) | BigQuery: `market_listings` | Step 4: Price comparison |
| **Pipeline_Regulation** | Official face values + state/provincial laws (Google Sheets) | BigQuery: `regulation_reference` | Step 5: Compliance check |
| **Pipeline_PhishDomain** | Phishing-Database (GitHub) + PhishHunt feed | BigQuery: `known_phishing_domains` | Step 1: Domain audit |

---

## Data Sources

See [data-sources.md](./data-sources.md) for the full breakdown of all data sources, APIs, and ingestion methods.

Key sources:
- 🏟️ **Match & Venue Data**: [wc26-mcp](https://github.com/jordanlyall/wc26-mcp) — 18 tools, zero API keys
- 💰 **Live Market Prices**: [SeatGeek API](https://seatgeek.github.io/) — free developer access
- 👁️ **Seat Views**: [A View From My Seat](https://aviewfrommyseat.com) — Browser-Use + Gemini Vision
- 🚨 **Phishing Domains**: [PhishHunt](https://phishunt.io/feed/) + [Phishing-Database](https://github.com/Phishing-Database/Phishing.Database)
- ⚖️ **Resale Laws**: Manually curated CSV covering all 16 FIFA 2026 venue jurisdictions

---

## Hackathon Track Alignment

| Judging Criterion | How TicketGuard Satisfies It |
|---|---|
| **Move Beyond Chat** | Agent executes a 6-step tool chain: browser access → domain check → DB query → vision analysis → regulation lookup → report generation |
| **Multi-Step Mission** | Full access-analyze-report loop; each step's output drives the next; user stays in control until final report |
| **Partner Power (Fivetran)** | 3 dedicated pipelines; sightline audit and price comparison are non-functional without Fivetran data |
| **Real-World Problem** | FIFA 2026 ticket fraud is a live, high-stakes problem — Final tickets at $8,000+ with no buyer protection tools |

---

## References

- PhishDetect (Devpost) — sandbox browser active-access pattern
- SentinelEye (Devpost) — multimodal visual security inspection
- PhishAgent (AAAI 2025 Oral, arxiv:2408.10738) — dual-source comparison architecture
- MultiPhishGuard (arxiv:2505.23803) — multi-agent weighted score aggregation
- wc26-mcp (GitHub) — World Cup 2026 match and venue data foundation

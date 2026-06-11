/**
 * Shared report contract between the TicketGuard backend and frontend.
 *
 * Mirrors the backend session-state shape: each analysis dimension returns
 * `{ score, flags, detail }` (see backend/core/state_keys.py). The frontend
 * aggregates those into a single report object for display.
 */

export type Verdict = "safe" | "caution" | "danger";

/** One analysis dimension result, matching the backend `*_RESULT` shape. */
export interface DimensionResult {
  /** 0–100, higher is safer. */
  score: number;
  /** Short machine-readable risk tags, e.g. "NEW_DOMAIN". */
  flags: string[];
  /** Human-readable explanation shown under the score. */
  detail: string;
}

export interface SeatInfo {
  section: string;
  row: string;
  seat: string;
}

export interface TicketReport {
  /** The audited listing URL. */
  url: string;
  /** e.g. "USA vs Mexico". */
  match: string;
  /** e.g. "MetLife Stadium". */
  venue: string;
  seat: SeatInfo;
  /** Listing price in USD. */
  listingPrice: number;
  /** Live market median (SeatGeek P50) in USD. */
  marketMedian: number;

  /**
   * Real analysis dimensions surfaced in the report. Only website credibility
   * is backed by live backend data (the threat-intel + agent audit); the other
   * mock dimensions (price/compliance/sightline) were removed since they had no
   * real data source. Price fairness is shown by the dedicated price panels.
   */
  dimensions: {
    websiteCredibility: DimensionResult;
  };

  /** Weighted aggregate score, 0–100. */
  overallScore: number;
  /** Overall risk band derived from the aggregate score. */
  verdict: Verdict;
  /** One-line buy / don't-buy recommendation. */
  recommendation: string;

  /**
   * Raw security-audit payload from POST /api/security/audit, when the report
   * was built from the live backend rather than mock data. Optional so the
   * mock report and older callers stay valid.
   */
  security?: SecurityAuditResponse;
}

/** Maps a 0–100 score to a coarse risk band. */
export function scoreToVerdict(score: number): Verdict {
  if (score >= 70) return "safe";
  if (score >= 40) return "caution";
  return "danger";
}

// ---------------------------------------------------------------------------
// Threat-intel panel types (independent from TicketReport / mock data)
// ---------------------------------------------------------------------------

/** One threat-intel source result from the backend pipeline. */
export interface ThreatSource {
  /** Source name, e.g. "VirusTotal", "Sucuri". */
  name: string;
  /**
   * true  → confirmed threat
   * false → confirmed clean
   * null  → intelligence context only (not a threat verdict)
   */
  threat: boolean | null;
  /** Human-readable summary from this source. */
  detail: string;
  /** Any extra source-native fields (rank, match_count, …). */
  [key: string]: unknown;
}

/** Raw response from POST /api/threat-intel. */
export interface ThreatIntelResult {
  status: "ok" | "unavailable";
  /** True if any finding source reported threat = true. */
  flagged: boolean;
  /** Sources that returned a threat verdict (threat = true | false). */
  findings: ThreatSource[];
  /** Sources that returned intelligence context (threat = null). */
  context: ThreatSource[];
  /** Space-joined summary of all source details. */
  detail: string;
}

// ---------------------------------------------------------------------------
// Security audit response (POST /api/security/audit)
// ---------------------------------------------------------------------------

/** The agent_audit block, present only when the grey zone escalated. */
export interface AgentAudit {
  status: "ok" | "error" | string;
  error?: string | null;
  [key: string]: unknown;
}

/**
 * Response from POST /api/security/audit — the threat-intel result enriched by
 * the orchestrator with a synthesized credibility score and (in the grey zone)
 * a browser+OSINT agent audit.
 */
export interface SecurityAuditResponse extends ThreatIntelResult {
  /** Synthesized credibility score, 0–100 (higher = safer). */
  score: number;
  /** Coarse band from the backend, e.g. "critical" | "high" | "medium" | "low". */
  risk_level: string;
  /** Human-readable score rationale. */
  score_explanation: string;
  /** Whether the score landed in the ambiguous band that triggers the agent. */
  grey_zone: boolean;
  /** Present only when the agent ran (grey zone). */
  agent_audit?: AgentAudit;
  /** Deep-link to the Phoenix trace for this audit, if telemetry is enabled. */
  phoenix_url?: string | null;
}


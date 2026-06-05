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

  /** Four weighted dimensions surfaced in the report. */
  dimensions: {
    websiteCredibility: DimensionResult;
    price: DimensionResult;
    compliance: DimensionResult;
    sightline: DimensionResult;
  };

  /** Weighted aggregate score, 0–100. */
  overallScore: number;
  /** Overall risk band derived from the aggregate score. */
  verdict: Verdict;
  /** One-line buy / don't-buy recommendation. */
  recommendation: string;
}

/** Maps a 0–100 score to a coarse risk band. */
export function scoreToVerdict(score: number): Verdict {
  if (score >= 70) return "safe";
  if (score >= 40) return "caution";
  return "danger";
}

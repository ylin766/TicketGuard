/**
 * OSINT social-opinion agent stream — frontend contract.
 *
 * Mirrors the SSE frames emitted by GET /api/osint/stream (see backend
 * osint_stream.py). Each frame is one `data: {...}` line.
 */

export interface OsintStartFrame {
  type: "start";
  url: string;
  agent: string;
  ts: number;
}

export interface OsintThinkingFrame {
  type: "thinking";
  step: number;
  text: string;
}

export interface OsintToolCallFrame {
  type: "tool_call";
  step: number;
  id: string;
  tool: string;
  /** Friendly name for the UI, e.g. "Reddit discussions". */
  label: string;
  /** Source platform, e.g. "Trustpilot · SiteJabber". */
  source: string;
  args: Record<string, unknown>;
  ts: number;
}

export interface OsintToolResultFrame {
  type: "tool_result";
  step: number;
  id: string;
  tool: string;
  /** Truncated preview of the tool's response. */
  preview: string;
  chars: number;
  duration_ms: number;
  ok: boolean;
}

export interface OsintTokensFrame {
  type: "tokens";
  step: number;
  prompt: number;
  completion: number;
  total: number;
}

export interface OsintReportFrame {
  type: "report";
  /** Parsed 0-100 trust score, or null if not found. */
  score: number | null;
  /** Rubric tier name, or null. */
  tier: string | null;
  /** The full structured report text. */
  text: string;
}

export interface OsintDoneFrame {
  type: "done";
  stats: {
    steps: number;
    tool_calls: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    duration_ms: number;
  };
  phoenix_url: string | null;
}

export interface OsintErrorFrame {
  type: "error";
  message: string;
}

export type OsintFrame =
  | OsintStartFrame
  | OsintThinkingFrame
  | OsintToolCallFrame
  | OsintToolResultFrame
  | OsintTokensFrame
  | OsintReportFrame
  | OsintDoneFrame
  | OsintErrorFrame;

/** A tool call merged with its result, for rendering as one trace step. */
export interface OsintStep {
  id: string;
  tool: string;
  label: string;
  source: string;
  args: Record<string, unknown>;
  /** "running" until the result frame arrives, then "ok" | "fail". */
  status: "running" | "ok" | "fail";
  durationMs: number | null;
  chars: number | null;
  preview: string | null;
}

/** Running token totals. */
export interface OsintTokenTotals {
  prompt: number;
  completion: number;
  total: number;
}

export type OsintStatus = "idle" | "streaming" | "done" | "error";

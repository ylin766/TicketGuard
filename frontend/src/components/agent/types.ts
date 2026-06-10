/**
 * AGENT social-opinion agent stream — frontend contract.
 *
 * Mirrors the SSE frames emitted by GET /api/osint/stream (see backend
 * agent_stream.py). Each frame is one `data: {...}` line.
 */

export interface AgentStartFrame {
  type: "start";
  url: string;
  agent: string;
  ts: number;
}

export interface AgentThinkingFrame {
  type: "thinking";
  step: number;
  text: string;
}

export interface AgentToolCallFrame {
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

export interface AgentToolResultFrame {
  type: "tool_result";
  step: number;
  id: string;
  tool: string;
  preview: string;
  /** Optional image URLs returned by the tool (for multimodal support). */
  images?: string[];
  chars: number;
  duration_ms: number;
  ok: boolean;
}

export interface AgentTokensFrame {
  type: "tokens";
  step: number;
  prompt: number;
  completion: number;
  total: number;
}

export interface AgentReportFrame {
  type: "report";
  /** Parsed 0-100 trust score, or null if not found. */
  score: number | null;
  /** Rubric tier name, or null. */
  tier: string | null;
  /** The full structured report text. */
  text: string;
}

export interface AgentDoneFrame {
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

export interface AgentErrorFrame {
  type: "error";
  message: string;
}

export type AgentFrame =
  | AgentStartFrame
  | AgentThinkingFrame
  | AgentToolCallFrame
  | AgentToolResultFrame
  | AgentTokensFrame
  | AgentReportFrame
  | AgentDoneFrame
  | AgentErrorFrame;

/** A tool call merged with its result, for rendering as one trace step. */
export interface AgentStep {
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
  images?: string[];
  /** Tokens spent on the model turn that decided this tool call (prompt+completion). */
  tokens: number | null;
}

/** Running token totals. */
export interface AgentTokenTotals {
  prompt: number;
  completion: number;
  total: number;
}

export type AgentStatus = "idle" | "streaming" | "done" | "error";

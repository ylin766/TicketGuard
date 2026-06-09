import { motion, AnimatePresence } from "framer-motion";
import type { OsintState } from "./useOsintStream";
import type { OsintStep } from "./types";
import "./OsintPanel.css";

/**
 * Social / public-opinion investigation agent — live multi-step trace.
 *
 * Renders the OSINT agent's run as a vertical "agent timeline" (the pattern
 * used by LangGraph Studio / Phoenix trace views): each tool call is a node
 * with an icon, friendly label, source platform, a live status pip and its
 * latency; a spine connects them and fills as the run progresses. A stats strip
 * surfaces the Arize/OpenInference telemetry (tokens, tool calls, elapsed). The
 * final structured report (0-100 trust score + rubric tier) lands at the end.
 */

const EASE = [0.22, 1, 0.36, 1] as const;

/* ---------- Tool icons (match the backend tool labels) ---------- */
function ToolIcon({ tool }: { tool: string }) {
  switch (tool) {
    case "search_consumer_reviews":
      return (
        <svg viewBox="0 0 24 24" className="osint-tool-svg" aria-hidden="true">
          <path d="M12 4l2.2 4.6 5 .7-3.6 3.5.9 5L12 15.9 7.5 17.8l.9-5L4.8 9.3l5-.7L12 4z" />
        </svg>
      );
    case "search_reddit_discussions":
      return (
        <svg viewBox="0 0 24 24" className="osint-tool-svg" aria-hidden="true">
          <circle cx="12" cy="13" r="7" />
          <circle cx="9.5" cy="12.5" r="1" fill="currentColor" stroke="none" />
          <circle cx="14.5" cy="12.5" r="1" fill="currentColor" stroke="none" />
          <path d="M9 15.5c1.8 1.2 4.2 1.2 6 0M12 6l1-3 3 .7" />
          <circle cx="19" cy="4" r="1.3" />
        </svg>
      );
    case "search_twitter_mentions":
      return (
        <svg viewBox="0 0 24 24" className="osint-tool-svg" aria-hidden="true">
          <path d="M5 5l6.5 8.5M5 19l6-6.5M13 11.5L19 19M13 11.5L18 5" />
        </svg>
      );
    case "search_general_opinions":
      return (
        <svg viewBox="0 0 24 24" className="osint-tool-svg" aria-hidden="true">
          <circle cx="11" cy="11" r="6.5" />
          <path d="M16 16l4 4" />
        </svg>
      );
    case "read_specific_url":
      return (
        <svg viewBox="0 0 24 24" className="osint-tool-svg" aria-hidden="true">
          <path d="M6 4h8l4 4v12H6z" />
          <path d="M14 4v4h4M9 13h6M9 16h6" />
        </svg>
      );
    default:
      return (
        <svg viewBox="0 0 24 24" className="osint-tool-svg" aria-hidden="true">
          <circle cx="12" cy="12" r="8" />
        </svg>
      );
  }
}

function StatusPip({ status }: { status: OsintStep["status"] }) {
  if (status === "running") {
    return <span className="osint-pip osint-pip--run" aria-label="Running" />;
  }
  if (status === "ok") {
    return (
      <svg viewBox="0 0 24 24" className="osint-pip osint-pip--ok" aria-label="Done">
        <path d="M5 12l4 4 10-10" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" className="osint-pip osint-pip--fail" aria-label="Failed">
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}

/** A single search query argument, shown as a quiet inline chip. */
function ArgChips({ args }: { args: Record<string, unknown> }) {
  const entries = Object.entries(args).filter(
    ([, v]) => v != null && String(v).trim() !== ""
  );
  if (entries.length === 0) return null;
  return (
    <div className="osint-args">
      {entries.map(([k, v]) => (
        <span key={k} className="osint-arg">
          {String(v)}
        </span>
      ))}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="osint-stat">
      <span className="osint-stat-value">{value}</span>
      <span className="osint-stat-label">{label}</span>
    </div>
  );
}

function fmtMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function OsintPanel({ state }: { state: OsintState }) {
  const { status, steps, thoughts, tokens, stats, report, phoenixUrl, error } = state;
  const live = status === "streaming";
  const latestThought = thoughts[thoughts.length - 1];
  const toolCalls = stats?.toolCalls ?? steps.length;
  const totalTokens = stats?.totalTokens ?? tokens.total;

  return (
    <div className="osint-panel">
      <div className="osint-head">
        <span className="osint-head-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" className="osint-tool-svg">
            <circle cx="11" cy="11" r="6.5" />
            <path d="M16 16l4 4" />
            <path d="M8.5 11h5M11 8.5v5" />
          </svg>
        </span>
        <span className="osint-head-titles">
          <span className="osint-head-title">Public Opinion Investigation</span>
          <span className="osint-head-sub">
            {status === "idle" && "Queued"}
            {live && (latestThought ? "Reasoning…" : "Investigating across the web…")}
            {status === "done" && `Investigation complete · ${toolCalls} sources checked`}
            {status === "error" && "Investigation unavailable"}
          </span>
        </span>
        {live && (
          <span className="osint-dots" aria-hidden="true">
            <span className="osint-dot" />
            <span className="osint-dot" />
            <span className="osint-dot" />
          </span>
        )}
        {report?.score != null && (
          <span className={`osint-score osint-score--${tierTone(report.score)}`}>
            {report.score}
          </span>
        )}
      </div>

      {/* Telemetry strip — the Arize/OpenInference trace metrics. */}
      <div className="osint-stats">
        <Stat label="tool calls" value={String(toolCalls)} />
        <Stat label="tokens" value={totalTokens > 0 ? compact(totalTokens) : "—"} />
        <Stat
          label="elapsed"
          value={stats ? fmtMs(stats.durationMs) : live ? "…" : "—"}
        />
      </div>

      {error && <div className="osint-error">{error}</div>}

      {/* The agent run timeline. */}
      {steps.length > 0 && (
        <div className={`osint-trace ${live ? "osint-trace--live" : ""}`}>
          <AnimatePresence initial={false}>
            {steps.map((s) => (
              <motion.div
                key={s.id}
                className={`osint-node osint-node--${s.status}`}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3, ease: EASE }}
              >
                <span className="osint-node-icon" aria-hidden="true">
                  <ToolIcon tool={s.tool} />
                </span>
                <div className="osint-node-body">
                  <div className="osint-node-headline">
                    <span className="osint-node-label">{s.label}</span>
                    {s.source && <span className="osint-node-source">{s.source}</span>}
                  </div>
                  <ArgChips args={s.args} />
                </div>
                <div className="osint-node-meta">
                  {s.durationMs != null && (
                    <span className="osint-node-dur">{fmtMs(s.durationMs)}</span>
                  )}
                  <StatusPip status={s.status} />
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Final structured verdict. */}
      {report && (
        <motion.div
          className="osint-verdict"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: EASE }}
        >
          <div className="osint-verdict-head">
            <span className="eyebrow">Trust assessment</span>
            {report.tier && (
              <span className={`osint-tier osint-tier--${tierTone(report.score ?? 50)}`}>
                {report.tier}
              </span>
            )}
          </div>
          {report.score != null && (
            <div className="osint-meter">
              <motion.span
                className={`osint-meter-fill osint-meter-fill--${tierTone(report.score)}`}
                initial={{ width: 0 }}
                animate={{ width: `${report.score}%` }}
                transition={{ duration: 0.6, ease: EASE }}
              />
            </div>
          )}
        </motion.div>
      )}

      {phoenixUrl && status === "done" && (
        <a
          className="osint-phoenix"
          href={phoenixUrl}
          target="_blank"
          rel="noreferrer noopener"
        >
          View full trace in Arize Phoenix →
        </a>
      )}
    </div>
  );
}

/** 0-100 trust score → tone (higher is safer). */
function tierTone(score: number): "danger" | "caution" | "safe" {
  if (score <= 40) return "danger";
  if (score <= 60) return "caution";
  return "safe";
}

/** Compact a token count, e.g. 1234 → "1.2k". */
function compact(n: number): string {
  if (n < 1000) return String(n);
  return `${(n / 1000).toFixed(1)}k`;
}

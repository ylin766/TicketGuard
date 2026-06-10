import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { AgentState } from "./useAgentStream";
import type { AgentStep } from "./types";
import "./AgentPanel.css";

/**
 * Social / public-opinion investigation agent — live multi-step trace.
 *
 * Renders the AGENT agent's run as a vertical "agent timeline" (the pattern
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
        <svg viewBox="0 0 24 24" className="agent-tool-svg" aria-hidden="true">
          <path d="M12 4l2.2 4.6 5 .7-3.6 3.5.9 5L12 15.9 7.5 17.8l.9-5L4.8 9.3l5-.7L12 4z" />
        </svg>
      );
    case "search_reddit_discussions":
      return (
        <svg viewBox="0 0 24 24" className="agent-tool-svg" aria-hidden="true">
          <circle cx="12" cy="13" r="7" />
          <circle cx="9.5" cy="12.5" r="1" fill="currentColor" stroke="none" />
          <circle cx="14.5" cy="12.5" r="1" fill="currentColor" stroke="none" />
          <path d="M9 15.5c1.8 1.2 4.2 1.2 6 0M12 6l1-3 3 .7" />
          <circle cx="19" cy="4" r="1.3" />
        </svg>
      );
    case "search_twitter_mentions":
      return (
        <svg viewBox="0 0 24 24" className="agent-tool-svg" aria-hidden="true">
          <path d="M5 5l6.5 8.5M5 19l6-6.5M13 11.5L19 19M13 11.5L18 5" />
        </svg>
      );
    case "search_general_opinions":
      return (
        <svg viewBox="0 0 24 24" className="agent-tool-svg" aria-hidden="true">
          <circle cx="11" cy="11" r="6.5" />
          <path d="M16 16l4 4" />
        </svg>
      );
    case "read_specific_url":
      return (
        <svg viewBox="0 0 24 24" className="agent-tool-svg" aria-hidden="true">
          <path d="M6 4h8l4 4v12H6z" />
          <path d="M14 4v4h4M9 13h6M9 16h6" />
        </svg>
      );
    default:
      return (
        <svg viewBox="0 0 24 24" className="agent-tool-svg" aria-hidden="true">
          <circle cx="12" cy="12" r="8" />
        </svg>
      );
  }
}

function StatusPip({ status }: { status: AgentStep["status"] }) {
  if (status === "running") {
    return <span className="agent-pip agent-pip--run" aria-label="Running" />;
  }
  if (status === "ok") {
    return (
      <svg viewBox="0 0 24 24" className="agent-pip agent-pip--ok" aria-label="Done">
        <path d="M5 12l4 4 10-10" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" className="agent-pip agent-pip--fail" aria-label="Failed">
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
    <div className="agent-args">
      {entries.map(([k, v]) => (
        <span key={k} className="agent-arg">
          {String(v)}
        </span>
      ))}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="agent-stat">
      <span className="agent-stat-value">{value}</span>
      <span className="agent-stat-label">{label}</span>
    </div>
  );
}

function fmtMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** A clay-morphism duration meter: a pressed-in groove with a poured-clay fill
 *  whose length maps to how long the step took (longer step = fuller bar),
 *  followed by the elapsed seconds. Gives time a tactile, material readout. */
const DUR_FULL_MS = 6000; // a step at/above this fills the whole groove
function DurationBar({ ms, tone }: { ms: number; tone: "ok" | "fail" }) {
  const pct = Math.max(8, Math.min(100, (ms / DUR_FULL_MS) * 100));
  return (
    <span className="agent-dur" title={`${ms} ms`}>
      <span className="agent-dur-track" aria-hidden="true">
        <span
          className={`agent-dur-fill agent-dur-fill--${tone}`}
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="agent-dur-num">{fmtMs(ms)}</span>
    </span>
  );
}

/** Compact a token count, e.g. 1234 → "1.2k". */
function compactTokens(n: number): string {
  if (n < 1000) return String(n);
  return `${(n / 1000).toFixed(1)}k`;
}

function getToolTheme(tool?: string): string {
  if (!tool) return "idle";
  if (tool.includes("reddit")) return "reddit";
  if (tool.includes("twitter")) return "twitter";
  if (tool.includes("reviews")) return "reviews";
  if (tool.includes("read_specific_url")) return "url";
  return "general";
}

/** 
 * Clean up noisy JSON/Python wrappers and URLs from the raw preview string,
 * leaving just the actual text snippet for the UI bubble.
 */
function extractSnippet(raw: string): string {
  let s = raw;
  // Naive cleanup of Python dict / JSON wrappers: {'result': '...'}
  s = s.replace(/^[\s\{\[]*(['"]?result['"]?\s*:\s*)?['"]?/, '');
  s = s.replace(/['"]?[\s\}\]]*$/, '');
  
  // Remove URLs
  s = s.replace(/https?:\/\/[^\s]+/g, '');
  // Remove common noisy prefixes
  s = s.replace(/(Title|URL Source|Record \d+|Content):/gi, '');
  // Replace newlines and slashes
  s = s.replace(/[\n\r\t\\]+/g, ' ');
  
  // Clean up extra spaces
  s = s.trim().replace(/\s{2,}/g, ' ');
  
  if (s.length < 5) return "Extracting data...";
  
  if (s.length > 55) {
    // Try to cut at a word boundary
    const cut = s.slice(0, 55);
    const lastSpace = cut.lastIndexOf(' ');
    if (lastSpace > 30) {
      return cut.slice(0, lastSpace) + "…";
    }
    return cut + "…";
  }
  return s;
}

export function AgentPanel({
  state,
  variant = "report",
}: {
  state: AgentState;
  variant?: "runtime" | "report";
}) {
  const { status, steps, thoughts, tokens, stats, report, phoenixUrl, error } = state;
  const live = status === "streaming";
  const latestThought = thoughts[thoughts.length - 1];
  const activeStep = steps.find(s => s.status === "running");
  const toolCalls = stats?.toolCalls ?? steps.length;
  const totalTokens = stats?.totalTokens ?? tokens.total;

  const recentPreviews = steps
    .filter(s => s.status === "ok" && s.preview)
    .slice(-2); // grab the last 2 successful tool results

  const [elapsedMs, setElapsedMs] = useState(0);
  useEffect(() => {
    if (!live) return;
    const start = Date.now();
    const interval = setInterval(() => {
      setElapsedMs(Date.now() - start);
    }, 100);
    return () => clearInterval(interval);
  }, [live]);

  let statusText = "Initialising agent…";
  if (activeStep) {
    statusText = `Running: ${activeStep.label}`;
  } else if (latestThought && latestThought.trim() !== "") {
    statusText = `Thinking: ${latestThought}`;
  } else if (steps.length > 0) {
    statusText = "Analyzing findings…";
  }

  return (
    <div className="agent-panel">
      <div className="agent-head">
        <span className="agent-head-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" className="agent-tool-svg">
            <circle cx="11" cy="11" r="6.5" />
            <path d="M16 16l4 4" />
            <path d="M8.5 11h5M11 8.5v5" />
          </svg>
        </span>
        <span className="agent-head-titles">
          <span className="agent-head-title">Public Opinion Investigation</span>
          <span className="agent-head-sub">
            {status === "idle" && "Queued"}
            {live && (latestThought ? "Reasoning…" : "Investigating across the web…")}
            {status === "done" && `Investigation complete · ${toolCalls} sources checked`}
            {status === "error" && "Investigation unavailable"}
          </span>
        </span>
        {live && (
          <span className="agent-dots" aria-hidden="true">
            <span className="agent-dot" />
            <span className="agent-dot" />
            <span className="agent-dot" />
          </span>
        )}
        {report?.score != null && (
          <span className={`agent-score agent-score--${tierTone(report.score)}`}>
            {report.score}
          </span>
        )}
      </div>

      {/* Telemetry strip — the Arize/OpenInference trace metrics. */}
      <div className="agent-stats">
        <Stat label="tool calls" value={String(toolCalls)} />
        <Stat label="tokens" value={totalTokens > 0 ? compact(totalTokens) : "—"} />
        <Stat
          label="elapsed"
          value={stats ? fmtMs(stats.durationMs) : live ? fmtMs(elapsedMs) : "—"}
        />
      </div>

      {error && <div className="agent-error">{error}</div>}

      {/* Runtime variant: Show looping 3D claymorphic animation instead of the trace list. */}
      {variant === "runtime" && (
        <div className={`agent-runtime-anim agent-theme--${getToolTheme(activeStep?.tool)}`}>
          
          {/* Floating snippets to visualize data extraction */}
          <div className="agent-floating-args">
            <AnimatePresence mode="popLayout">
              {recentPreviews.map((s) => (
                <motion.div
                  key={`preview-${s.id}`}
                  className="agent-floating-arg agent-floating-arg--snippet"
                  initial={{ opacity: 0, y: 15, scale: 0.8 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -15, scale: 0.8 }}
                  transition={{ duration: 0.6, ease: "backOut" }}
                >
                  "{extractSnippet(s.preview!)}"
                </motion.div>
              ))}
              {activeStep &&
                Object.entries(activeStep.args).map(([k, v]) => {
                  if (v == null || String(v).trim() === "") return null;
                  return (
                    <motion.div
                      key={`${activeStep.id}-${k}`}
                      className="agent-floating-arg agent-floating-arg--query"
                      initial={{ opacity: 0, y: 15, scale: 0.8 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: -15, scale: 0.8 }}
                      transition={{ duration: 0.5, ease: "backOut", delay: 0.1 }}
                    >
                      <span className="agent-floating-label">Searching:</span> {String(v)}
                    </motion.div>
                  );
                })}
            </AnimatePresence>
          </div>

          <div className="agent-blob-stage">
            {/* Expanding sonar rings when an agent tool is running */}
            {activeStep && (
              <div className="agent-sonar-container">
                <div className="agent-sonar-ring agent-sonar-ring-1" />
                <div className="agent-sonar-ring agent-sonar-ring-2" />
                <div className="agent-sonar-ring agent-sonar-ring-3" />
              </div>
            )}
            <motion.div
              className="agent-clay-blob"
              animate={{
                rotate: [0, 90, 180, 270, 360],
                borderRadius: [
                  "40% 60% 70% 30%",
                  "50% 50% 30% 70%",
                  "60% 40% 50% 50%",
                  "40% 60% 70% 30%",
                ],
              }}
              transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
            />
            <motion.div
              className="agent-clay-blob-inner"
              animate={{
                rotate: [360, 270, 180, 90, 0],
                borderRadius: [
                  "50% 50% 30% 70%",
                  "40% 60% 70% 30%",
                  "60% 40% 50% 50%",
                  "50% 50% 30% 70%",
                ],
              }}
              transition={{ duration: 3.5, repeat: Infinity, ease: "linear" }}
            />
            {/* The icon is decoupled from the rotating blobs, and pulses slightly. */}
            <motion.div
              className="agent-blob-icon-container"
              animate={{ scale: [1, 1.15, 1], y: [-2, 2, -2] }}
              transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            >
              {activeStep ? (
                <ToolIcon tool={activeStep.tool} />
              ) : (
                <svg viewBox="0 0 24 24" className="agent-idle-icon" aria-hidden="true">
                  <circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" strokeWidth="2" />
                  <path d="M16 16l4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              )}
            </motion.div>
          </div>
          <div className="agent-anim-status">
            <span className="agent-anim-pulse" aria-hidden="true" />
            <span className="agent-anim-text">
              {statusText}
            </span>
          </div>
        </div>
      )}

      {/* The agent run timeline. */}
      {variant === "report" && steps.length > 0 && (
        <div className={`agent-trace ${live ? "agent-trace--live" : ""}`}>
          <AnimatePresence initial={false}>
            {steps.map((s) => (
              <motion.div
                key={s.id}
                className={`agent-node agent-node--${s.status}`}
                data-tool={s.tool}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3, ease: EASE }}
              >
                <span className="agent-node-icon" aria-hidden="true">
                  <ToolIcon tool={s.tool} />
                </span>
                <div className="agent-node-body">
                  <div className="agent-node-headline">
                    <span className="agent-node-label">{s.label}</span>
                    {s.source && <span className="agent-node-source">{s.source}</span>}
                  </div>
                  <ArgChips args={s.args} />
                  {s.images && s.images.length > 0 && (
                    <div className="agent-node-images">
                      {s.images.map((url, i) => (
                        <div key={i} className="agent-clay-image-wrap">
                          <img src={url} alt="Agent visual observation" className="agent-clay-image" loading="lazy" />
                        </div>
                      ))}
                    </div>
                  )}
                  {/* Per-step cost readout, shown once the step has finished:
                      a clay duration meter (length ∝ time) + the token spend. */}
                  {s.status !== "running" && (
                    <div className="agent-node-cost">
                      {s.durationMs != null && (
                        <DurationBar
                          ms={s.durationMs}
                          tone={s.status === "fail" ? "fail" : "ok"}
                        />
                      )}
                      {s.tokens != null && s.tokens > 0 && (
                        <span className="agent-node-tok">
                          <span className="agent-node-tok-dot" aria-hidden="true" />
                          {compactTokens(s.tokens)} tok
                        </span>
                      )}
                    </div>
                  )}
                </div>
                <div className="agent-node-meta">
                  <StatusPip status={s.status} />
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Final structured verdict. */}
      {variant === "report" && report && (
        <motion.div
          className="agent-verdict"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: EASE }}
        >
          <div className="agent-verdict-head">
            <span className="eyebrow">Trust assessment</span>
            {report.tier && (
              <span className={`agent-tier agent-tier--${tierTone(report.score ?? 50)}`}>
                {report.tier}
              </span>
            )}
          </div>
          {report.score != null && (
            <div className="agent-meter">
              <motion.span
                className={`agent-meter-fill agent-meter-fill--${tierTone(report.score)}`}
                initial={{ width: 0 }}
                animate={{ width: `${report.score}%` }}
                transition={{ duration: 0.6, ease: EASE }}
              />
            </div>
          )}
        </motion.div>
      )}

      {variant === "report" && phoenixUrl && status === "done" && (
        <a
          className="agent-phoenix"
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

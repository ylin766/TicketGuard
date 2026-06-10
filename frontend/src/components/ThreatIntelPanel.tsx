import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { ThreatSource } from "../types";
import { SourcePanel, SourcePanelSkeleton, SourcePanelTimeout } from "./threatintel/SourcePanel";
import { GlyphShield, GlyphChevron } from "./threatintel/icons";
import "./ThreatIntelPanel.css";

/** Verdict summary passed to onDone so callers can score-gate what comes next
 *  (e.g. only escalate to the opinion agent for grey-zone results). */
export interface ThreatScanSummary {
  /** Backend's aggregate flag: any source reported a threat. */
  flagged: boolean;
  /** Number of sources that returned threat = true. */
  alerts: number;
  /** Number of sources that returned any verdict (true/false). */
  reported: number;
  /** Authoritative score (0-100) computed by the backend, when available. */
  score?: number | null;
  /** Backend's grey-zone decision — the single source of truth for whether the
   *  Layer-2 agent should run. The frontend no longer re-derives this. */
  greyZone?: boolean;
}

/** Full scan result cache passed from the pipeline phase to the report. Carries
 *  everything the report needs so it can be assembled WITHOUT re-running the
 *  backend: the streamed sources plus the authoritative score / grey-zone /
 *  explanation from the stream's `done` frame. */
export interface ThreatScanCache {
  sources: import("../types").ThreatSource[];
  flagged: boolean;
  /** Authoritative credibility score (0-100), or null when unavailable. */
  score: number | null;
  /** Backend risk band, e.g. "high" | "medium" | "low" (may be empty). */
  riskLevel: string;
  /** Human-readable score rationale (may be empty). */
  scoreExplanation: string;
  /** Backend grey-zone decision — whether the Layer-2 agent ran. */
  greyZone: boolean;
}

interface ThreatIntelPanelProps {
  url: string;
  /** Fired once the stream settles (done / unavailable / error) — used by the
   *  cinematic flow to advance past the pipeline phase on real completion.
   *  Receives a verdict summary for score-gating the next step. */
  onDone?: (summary: ThreatScanSummary) => void;
  /** Compact mode: single column, head-only source rows — fits a narrow 1/3
   *  column without an inner scrollbar. */
  compact?: boolean;
  /** Runtime mode: a minimal live readout for the pipeline phase — just the
   *  scanning animation, progress and the basic verdict. The full source list
   *  is reserved for the report. */
  variant?: "full" | "runtime";
  /**
   * Pre-fetched sources from the pipeline phase. When provided the component
   * skips the network stream and renders the cached data directly as "done".
   */
  cachedSources?: ThreatSource[];
  cachedFlagged?: boolean;
  /** Called when the stream completes, passing the full scan cache (sources +
   *  authoritative score/grey-zone/explanation). Use this in the pipeline stage
   *  to build the cache the report page renders from — no re-fetch on report. */
  onComplete?: (cache: ThreatScanCache) => void;
}

const STREAM_ENDPOINT = "http://localhost:8001/api/threat-intel/stream";

/** Known source manifest (matches the backend ALL_SOURCES order) so skeleton
 *  placeholders render immediately and are swapped in place as results stream,
 *  keeping the layout stable. Each entry notes its group. */
const FINDING_SOURCES = [
  "VirusTotal",
  "SafeBrowsing",
  "URLhaus",
  "CheckPhish",
  "MetaDefender",
  "Sucuri",
  "OpenPhish",
  "PhishStats",
] as const;
const CONTEXT_SOURCES = ["Tranco", "crt.sh", "Wayback", "RDAP", "IPGeo"] as const;

/** Sources that carry a threat verdict render in the "scan" group; the rest
 *  (threat === null) are intelligence context. */
function isFinding(source: ThreatSource): boolean {
  return source.threat === true || source.threat === false;
}

// Three pulsing clay dots for the streaming state.
function ClayDots() {
  return (
    <span className="ti-clay-dots" aria-label="Loading">
      <span className="ti-dot" />
      <span className="ti-dot" />
      <span className="ti-dot" />
    </span>
  );
}

/**
 * A titled group. While streaming, every manifest source renders as its arrived
 * panel or a themed skeleton, so the grid never shifts. Once done, sources that
 * never returned render an explicit "timed out" panel instead of vanishing.
 */
function Group({
  title,
  manifest,
  arrived,
  streaming,
  compact,
}: {
  title: string;
  manifest: readonly string[];
  arrived: Map<string, ThreatSource>;
  streaming: boolean;
  compact?: boolean;
}) {
  return (
    <div className="ti-group">
      <span className="ti-group-title eyebrow">{title}</span>
      <div className="ti-group-grid">
        {manifest.map((name, i) => {
          const src = arrived.get(name);
          return (
            <motion.div
              key={name}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                duration: 0.28,
                delay: Math.min(i * 0.04, 0.3),
                ease: [0.22, 1, 0.36, 1],
              }}
            >
              {src ? (
                <SourcePanel source={src} compact={compact} />
              ) : streaming ? (
                <SourcePanelSkeleton name={name} compact={compact} />
              ) : (
                <SourcePanelTimeout name={name} compact={compact} />
              )}
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

type StreamStatus = "idle" | "streaming" | "done" | "error" | "unavailable";

export function ThreatIntelPanel({
  url,
  onDone,
  compact,
  variant = "full",
  cachedSources,
  cachedFlagged,
  onComplete,
}: ThreatIntelPanelProps) {
  // If we have cached data, start directly in "done" state — no stream.
  const [sources, setSources] = useState<ThreatSource[]>(cachedSources ?? []);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>(
    cachedSources ? "done" : "idle"
  );
  const [flagged, setFlagged] = useState<boolean | null>(
    cachedSources ? (cachedFlagged ?? false) : null
  );
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(true);
  const controllerRef = useRef<AbortController | null>(null);
  // Keep the latest onDone without re-running the stream effect.
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;
  const doneFiredRef = useRef(false);
  // Live verdict tallies (refs so the stream closure reads fresh values).
  const alertsRef = useRef(0);
  const reportedRef = useRef(0);
  const flaggedRef = useRef(false);
  // Authoritative score + grey-zone decision from the backend done frame.
  const scoreRef = useRef<number | null>(null);
  const greyZoneRef = useRef(false);
  const riskLevelRef = useRef("");
  const scoreExplanationRef = useRef("");
  // Accumulates all received sources so onComplete gets the full list.
  const sourcesRef = useRef<ThreatSource[]>([]);

  useEffect(() => {
    // Skip streaming if cached data was provided.
    if (cachedSources) return;

    setSources([]);
    setFlagged(null);
    setErrorMsg(null);
    setStreamStatus("streaming");
    setExpanded(true);
    doneFiredRef.current = false;
    alertsRef.current = 0;
    reportedRef.current = 0;
    flaggedRef.current = false;
    scoreRef.current = null;
    greyZoneRef.current = false;
    riskLevelRef.current = "";
    scoreExplanationRef.current = "";

    const controller = new AbortController();
    controllerRef.current = controller;

    const fireDone = () => {
      if (doneFiredRef.current) return;
      doneFiredRef.current = true;
      onCompleteRef.current?.({
        sources: sourcesRef.current,
        flagged: flaggedRef.current,
        score: scoreRef.current,
        riskLevel: riskLevelRef.current,
        scoreExplanation: scoreExplanationRef.current,
        greyZone: greyZoneRef.current,
      });
      onDoneRef.current?.({
        flagged: flaggedRef.current,
        alerts: alertsRef.current,
        reported: reportedRef.current,
        score: scoreRef.current,
        greyZone: greyZoneRef.current,
      });
    };

    const streamUrl = `${STREAM_ENDPOINT}?url=${encodeURIComponent(url)}`;

    fetch(streamUrl, { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`Server error ${res.status}`);
        if (!res.body) throw new Error("No response body");

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const json = line.slice(6).trim();
            if (!json) continue;

            const event = JSON.parse(json) as {
              type: "source" | "done";
              data?: ThreatSource;
              status?: string;
              flagged?: boolean;
              score?: number | null;
              risk_level?: string | null;
              score_explanation?: string;
              grey_zone?: boolean;
            };

            if (event.type === "source" && event.data) {
              const src = event.data;
              sourcesRef.current = [...sourcesRef.current, src];
              setSources((prev) => [...prev, src]);

              if (src.threat === true || src.threat === false) {
                reportedRef.current += 1;
                if (src.threat === true) alertsRef.current += 1;
              }
            } else if (event.type === "done") {
              flaggedRef.current = event.flagged ?? false;
              scoreRef.current = event.score ?? null;
              greyZoneRef.current = event.grey_zone ?? false;
              riskLevelRef.current = event.risk_level ?? "";
              scoreExplanationRef.current = event.score_explanation ?? "";
              setFlagged(event.flagged ?? false);
              setStreamStatus(event.status === "unavailable" ? "unavailable" : "done");
              fireDone();
            }
          }
        }
      })
      .catch((err: Error) => {
        if (err.name === "AbortError") return;
        setErrorMsg(err.message);
        setStreamStatus("error");
        fireDone();
      });

    return () => controller.abort();
  }, [url]);

  const isStreaming = streamStatus === "streaming";
  const isDone = streamStatus === "done";

  const findings = sources.filter(isFinding);
  const context = sources.filter((s) => !isFinding(s));
  const alerts = findings.filter((s) => s.threat === true).length;
  const passed = findings.filter((s) => s.threat === false).length;

  // Index arrived sources by name so groups can swap skeletons in place.
  const arrived = new Map(sources.map((s) => [s.name, s]));
  const totalSources = FINDING_SOURCES.length + CONTEXT_SOURCES.length;

  // ----- Runtime variant: minimal live readout (animation + basic info) -----
  if (variant === "runtime") {
    const pct = Math.round((sources.length / totalSources) * 100);
    return (
      <div className="ti-panel ti-panel--runtime glass">
        <div className="ti-rt-head">
          <span className="ti-header-icon-wrap">
            <GlyphShield className="ti-header-shield" />
          </span>
          <span className="ti-header-titles">
            <span className="ti-header-title">Threat Intelligence</span>
            <span className="ti-header-sub">
              {isStreaming ? (
                <>Scanning… {sources.length} / {totalSources} sources</>
              ) : isDone || streamStatus === "unavailable" ? (
                <>
                  {passed} passed
                  {alerts > 0 ? ` · ${alerts} flagged` : ""} · {context.length}{" "}
                  signals
                </>
              ) : streamStatus === "error" ? (
                <>Connection error</>
              ) : (
                <>Idle</>
              )}
            </span>
          </span>
          {isStreaming && <ClayDots />}
          {isDone && flagged !== null && (
            <span className={`ti-badge ${flagged ? "ti-badge--danger" : "ti-badge--safe"}`}>
              {flagged ? "FLAGGED" : "CLEAN"}
            </span>
          )}
        </div>

        {/* Live progress bar — the runtime's main motion. */}
        <div className="ti-rt-bar" role="progressbar" aria-valuenow={pct}>
          <motion.span
            className="ti-rt-bar-fill"
            animate={{ width: `${isDone ? 100 : pct}%` }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          />
          {isStreaming && <span className="ti-rt-bar-sheen" aria-hidden="true" />}
        </div>

        {/* Compact multi-column grid of every source — same colours, icons and
            loaders as the full report, just head-only rows. */}
        <div className="ti-rt-grid">
          {[...FINDING_SOURCES, ...CONTEXT_SOURCES].map((name, i) => {
            const src = arrived.get(name);
            return (
              <motion.div
                key={name}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  duration: 0.26,
                  delay: Math.min(i * 0.03, 0.25),
                  ease: [0.22, 1, 0.36, 1],
                }}
              >
                {src ? (
                  <SourcePanel source={src} compact />
                ) : isStreaming ? (
                  <SourcePanelSkeleton name={name} compact />
                ) : (
                  <SourcePanelTimeout name={name} compact />
                )}
              </motion.div>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className={`ti-panel glass${compact ? " ti-panel--compact" : ""}`}>
      {/* Header / verdict summary */}
      <button
        className="ti-header"
        onClick={() => setExpanded((v) => !v)}
        type="button"
        aria-expanded={expanded}
        disabled={sources.length === 0 && !isDone}
      >
        <span className="ti-header-left">
          <span className="ti-header-icon-wrap">
            <GlyphShield className="ti-header-shield" />
          </span>
          <span className="ti-header-titles">
            <span className="ti-header-title">Threat Intelligence</span>
            <span className="ti-header-sub">
              {isStreaming ? (
                <>Scanning… {sources.length} / {totalSources} sources</>
              ) : isDone || streamStatus === "unavailable" ? (
                <>
                  {passed} passed
                  {alerts > 0 ? ` · ${alerts} flagged` : ""} · {context.length}{" "}
                  signals
                </>
              ) : (
                <>Idle</>
              )}
            </span>
          </span>
          {isStreaming && <ClayDots />}
          {isDone && flagged !== null && (
            <span className={`ti-badge ${flagged ? "ti-badge--danger" : "ti-badge--safe"}`}>
              {flagged ? "FLAGGED" : "CLEAN"}
            </span>
          )}
        </span>
        {sources.length > 0 && <GlyphChevron expanded={expanded} />}
      </button>

      {/* Error */}
      {streamStatus === "error" && (
        <div className="ti-status ti-status--error">
          Could not reach the threat-intel server: {errorMsg}
        </div>
      )}

      {/* Unavailable */}
      {streamStatus === "unavailable" && sources.length === 0 && (
        <div className="ti-status">
          No threat-intel sources returned a result. Check that API keys are configured.
        </div>
      )}

      {/* Grouped source panels */}
      <AnimatePresence initial={false}>
        {expanded && (isStreaming || sources.length > 0) && (
          <motion.div
            className="ti-groups"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          >
            <Group
              title="Threat scan"
              manifest={FINDING_SOURCES}
              arrived={arrived}
              streaming={isStreaming}
              compact={compact}
            />
            <Group
              title="Domain intelligence"
              manifest={CONTEXT_SOURCES}
              arrived={arrived}
              streaming={isStreaming}
              compact={compact}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

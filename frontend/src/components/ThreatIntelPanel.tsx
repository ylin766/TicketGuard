import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { ThreatSource } from "../types";
import { SourcePanel } from "./threatintel/SourcePanel";
import { GlyphShield, GlyphChevron } from "./threatintel/icons";
import "./ThreatIntelPanel.css";

interface ThreatIntelPanelProps {
  url: string;
}

const STREAM_ENDPOINT = "http://localhost:8001/api/threat-intel/stream";

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

// A titled group of source panels.
function Group({ title, sources }: { title: string; sources: ThreatSource[] }) {
  if (sources.length === 0) return null;
  return (
    <div className="ti-group">
      <span className="ti-group-title eyebrow">{title}</span>
      <div className="ti-group-grid">
        {sources.map((src, i) => (
          <motion.div
            key={src.name}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: 0.28,
              delay: Math.min(i * 0.04, 0.3),
              ease: [0.22, 1, 0.36, 1],
            }}
          >
            <SourcePanel source={src} />
          </motion.div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

type StreamStatus = "idle" | "streaming" | "done" | "error" | "unavailable";

export function ThreatIntelPanel({ url }: ThreatIntelPanelProps) {
  const [sources, setSources] = useState<ThreatSource[]>([]);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("idle");
  const [flagged, setFlagged] = useState<boolean | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(true);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setSources([]);
    setFlagged(null);
    setErrorMsg(null);
    setStreamStatus("streaming");
    setExpanded(true);

    const controller = new AbortController();
    controllerRef.current = controller;

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
            };

            if (event.type === "source" && event.data) {
              setSources((prev) => [...prev, event.data!]);
            } else if (event.type === "done") {
              setFlagged(event.flagged ?? false);
              setStreamStatus(event.status === "unavailable" ? "unavailable" : "done");
            }
          }
        }
      })
      .catch((err: Error) => {
        if (err.name === "AbortError") return;
        setErrorMsg(err.message);
        setStreamStatus("error");
      });

    return () => controller.abort();
  }, [url]);

  const isStreaming = streamStatus === "streaming";
  const isDone = streamStatus === "done";

  const findings = sources.filter(isFinding);
  const context = sources.filter((s) => !isFinding(s));
  const alerts = findings.filter((s) => s.threat === true).length;
  const passed = findings.filter((s) => s.threat === false).length;

  return (
    <div className="ti-panel glass">
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
                <>Scanning… {sources.length} sources in</>
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
        {expanded && sources.length > 0 && (
          <motion.div
            className="ti-groups"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          >
            <Group title="Threat scan" sources={findings} />
            <Group title="Domain intelligence" sources={context} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

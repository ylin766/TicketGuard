import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { ThreatSource } from "../types";
import "./ThreatIntelPanel.css";

interface ThreatIntelPanelProps {
  url: string;
}

const STREAM_ENDPOINT = "http://localhost:8001/api/threat-intel/stream";

// ---------------------------------------------------------------------------
// SVG Icons — inline, no emoji, clay-compatible
// ---------------------------------------------------------------------------

function IconShield() {
  return (
    <svg className="ti-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 2L4 6v6c0 5.25 3.5 10.15 8 11.35C16.5 22.15 20 17.25 20 12V6L12 2z"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconCheck() {
  return (
    <svg className="ti-source-icon-svg ti-icon--safe" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" strokeWidth="1.8" />
      <path d="M8 12l3 3 5-5" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconAlert() {
  return (
    <svg className="ti-source-icon-svg ti-icon--danger" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" strokeWidth="1.8" />
      <path d="M12 8v4M12 16h.01" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function IconInfo() {
  return (
    <svg className="ti-source-icon-svg ti-icon--info" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" strokeWidth="1.8" />
      <path d="M12 11v5M12 8h.01" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function IconChevron({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`ti-chevron-svg ${expanded ? "ti-chevron-svg--up" : ""}`}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <path d="M6 9l6 6 6-6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// Three pulsing clay dots for loading state
function ClayDots() {
  return (
    <span className="ti-clay-dots" aria-label="Loading">
      <span className="ti-dot" />
      <span className="ti-dot" />
      <span className="ti-dot" />
    </span>
  );
}

// ---------------------------------------------------------------------------
// Source row
// ---------------------------------------------------------------------------

function sourceIconComponent(source: ThreatSource) {
  if (source.threat === true) return <IconAlert />;
  if (source.threat === false) return <IconCheck />;
  return <IconInfo />;
}

function sourceRowClass(source: ThreatSource): string {
  if (source.threat === true) return "ti-source ti-source--danger";
  if (source.threat === false) return "ti-source ti-source--safe";
  return "ti-source ti-source--info";
}

function SourceRow({ source, index }: { source: ThreatSource; index: number }) {
  return (
    <motion.div
      className={sourceRowClass(source)}
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.28, delay: index * 0.04, ease: [0.22, 1, 0.36, 1] }}
    >
      <span className="ti-source-icon-wrap">{sourceIconComponent(source)}</span>
      <div className="ti-source-body">
        <span className="ti-source-name">{source.name}</span>
        <span className="ti-source-detail">{source.detail}</span>
      </div>
    </motion.div>
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
  const [expanded, setExpanded] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setSources([]);
    setFlagged(null);
    setErrorMsg(null);
    setStreamStatus("streaming");
    setExpanded(false);

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
              setExpanded(true);
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

  return (
    <div className="ti-panel glass">
      {/* Header */}
      <button
        className="ti-header"
        onClick={() => setExpanded((v) => !v)}
        type="button"
        aria-expanded={expanded}
        disabled={sources.length === 0 && !isDone}
      >
        <span className="ti-header-left">
          <span className="ti-header-icon-wrap">
            <IconShield />
          </span>
          <span className="ti-header-title">Threat Intel Sources</span>
          {isStreaming && <ClayDots />}
          {isDone && flagged !== null && (
            <span className={`ti-badge ${flagged ? "ti-badge--danger" : "ti-badge--safe"}`}>
              {flagged ? "FLAGGED" : "CLEAN"}
            </span>
          )}
          {sources.length > 0 && (
            <span className="ti-count">{sources.length}</span>
          )}
        </span>
        {sources.length > 0 && <IconChevron expanded={expanded} />}
      </button>

      {/* Error */}
      {streamStatus === "error" && (
        <div className="ti-status ti-status--error">
          Could not reach the threat-intel server: {errorMsg}
        </div>
      )}

      {/* Unavailable */}
      {streamStatus === "unavailable" && (
        <div className="ti-status">
          No threat-intel sources returned a result. Check that API keys are configured.
        </div>
      )}

      {/* Source rows — appear one by one as stream delivers them */}
      <AnimatePresence>
        {expanded && sources.length > 0 && (
          <motion.div
            className="ti-sources"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          >
            {sources.map((src, i) => (
              <SourceRow key={src.name} source={src} index={i} />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

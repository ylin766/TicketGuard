import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { ThreatIntelResult, ThreatSource } from "../types";
import "./ThreatIntelPanel.css";

interface ThreatIntelPanelProps {
  url: string;
}

const THREAT_INTEL_ENDPOINT = "http://localhost:8001/api/threat-intel";

function sourceIcon(source: ThreatSource): string {
  if (source.threat === true) return "🚨";
  if (source.threat === false) return "✅";
  return "ℹ️";
}

function sourceClass(source: ThreatSource): string {
  if (source.threat === true) return "ti-source--danger";
  if (source.threat === false) return "ti-source--safe";
  return "ti-source--info";
}

function SourceRow({ source }: { source: ThreatSource }) {
  return (
    <div className={`ti-source ${sourceClass(source)}`}>
      <span className="ti-source-icon" aria-hidden="true">
        {sourceIcon(source)}
      </span>
      <div className="ti-source-body">
        <span className="ti-source-name">{source.name}</span>
        <span className="ti-source-detail">{source.detail}</span>
      </div>
    </div>
  );
}

export function ThreatIntelPanel({ url }: ThreatIntelPanelProps) {
  const [data, setData] = useState<ThreatIntelResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setData(null);

    fetch(THREAT_INTEL_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    })
      .then((res) => {
        if (!res.ok) throw new Error(`Server error ${res.status}`);
        return res.json() as Promise<ThreatIntelResult>;
      })
      .then(setData)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [url]);

  const allSources = data
    ? [...data.findings, ...data.context]
    : [];

  return (
    <div className="ti-panel glass">
      {/* Header row */}
      <button
        className="ti-header"
        onClick={() => setExpanded((v) => !v)}
        type="button"
        aria-expanded={expanded}
      >
        <span className="ti-header-left">
          <span className="ti-header-icon" aria-hidden="true">🛡️</span>
          <span className="ti-header-title">Threat Intel Sources</span>
          {data && (
            <span
              className={`ti-badge ${data.flagged ? "ti-badge--danger" : "ti-badge--safe"}`}
            >
              {data.flagged ? "FLAGGED" : "CLEAN"}
            </span>
          )}
        </span>
        <span className="ti-chevron" aria-hidden="true">
          {expanded ? "▲" : "▼"}
        </span>
      </button>

      {/* Loading state */}
      {loading && (
        <div className="ti-status">
          <span className="ti-spinner" aria-hidden="true">⏳</span>
          <span>Running threat intelligence checks…</span>
        </div>
      )}

      {/* Error state */}
      {!loading && error && (
        <div className="ti-status ti-status--error">
          <span aria-hidden="true">⚠️</span>
          <span>Could not reach the threat-intel server: {error}</span>
        </div>
      )}

      {/* Unavailable state */}
      {!loading && data?.status === "unavailable" && (
        <div className="ti-status">
          <span aria-hidden="true">🔌</span>
          <span>No threat-intel sources returned a result (no API keys configured?).</span>
        </div>
      )}

      {/* Source rows */}
      <AnimatePresence>
        {expanded && !loading && data?.status === "ok" && (
          <motion.div
            className="ti-sources"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          >
            {allSources.map((src) => (
              <SourceRow key={src.name} source={src} />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

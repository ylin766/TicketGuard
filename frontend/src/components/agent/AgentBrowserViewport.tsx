import { motion, AnimatePresence } from "framer-motion";
import type { BrowserCheckState } from "./useBrowserCheckStream";
import { BrowserFindings } from "./BrowserFindings";
import "../price/LiveBrowserViewport.css";

/**
 * Clay "viewport" that plays the Layer-2 browser-check agent's live screenshots
 * as it explores a suspicious ticket site (login / checkout / transfer surfaces),
 * then shows the verdict. Reuses the price viewport's clay styling.
 */

const EASE = [0.22, 1, 0.36, 1] as const;

const VERDICT_TONE: Record<string, string> = {
  dangerous: "bad",
  high: "bad",
  suspicious: "warn",
  medium: "warn",
  caution: "warn",
  safe: "good",
  low: "good",
};

export function AgentBrowserViewport({ state }: { state: BrowserCheckState }) {
  const {
    status,
    latestFrame,
    action,
    verdict,
    riskLevel,
    summary,
    brand,
    sensitiveSurfaces,
    error,
  } = state;
  const live = status === "streaming";
  const tone = riskLevel ? VERDICT_TONE[riskLevel.toLowerCase()] ?? "" : "";

  return (
    <div className="lbv">
      <div className="lbv-head">
        <span className="lbv-dot-row" aria-hidden="true">
          <span className="lbv-tdot lbv-tdot--r" />
          <span className="lbv-tdot lbv-tdot--y" />
          <span className="lbv-tdot lbv-tdot--g" />
        </span>
        <span className="lbv-title">Live security probe</span>
        {live && (
          <span className="lbv-live" aria-hidden="true">
            <span className="lbv-live-dot" /> LIVE
          </span>
        )}
        {status === "done" && <span className="lbv-badge">DONE</span>}
      </div>

      <div className="lbv-screen">
        <AnimatePresence mode="popLayout">
          {latestFrame ? (
            <motion.img
              key={latestFrame.step}
              className="lbv-frame"
              src={latestFrame.image}
              alt={latestFrame.action}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25, ease: EASE }}
            />
          ) : (
            <div className="lbv-skeleton" aria-label="Loading">
              <span className="lbv-scan" />
            </div>
          )}
        </AnimatePresence>
        {error && <div className="lbv-error">{error}</div>}
      </div>

      <div className="lbv-foot">
        <span className="lbv-action">
          {error
            ? "Security probe unavailable"
            : status === "done"
              ? summary || "Investigation complete"
              : action || (live ? "Opening site…" : "Queued")}
        </span>
        {verdict && (
          <span className={`lbv-result lbv-verdict--${tone}`}>
            <span className="lbv-result-median">{riskLevel ?? verdict}</span>
            <span className="lbv-result-label">{verdict}</span>
          </span>
        )}
      </div>

      {/* Structured findings live INSIDE the clay frame as a footer (like the
          price frame's median stat), not as a separate card below it. */}
      {status === "done" && (
        <BrowserFindings
          brand={brand}
          surfaces={sensitiveSurfaces}
          variant="frame"
        />
      )}
    </div>
  );
}

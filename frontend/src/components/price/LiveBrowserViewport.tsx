import { motion, AnimatePresence } from "framer-motion";
import type { PriceState } from "./usePriceStream";
import "./LiveBrowserViewport.css";

/**
 * A clay-morphism "viewport" that plays the headed browser's live screenshot
 * stream — the user watches the agent's eyes inside a clay frame instead of a
 * raw OS window popping up. Reusable: any screenshot-streaming flow (price now,
 * security browser-check later) can feed it a frame + action + result.
 */

const EASE = [0.22, 1, 0.36, 1] as const;

function fmtUsd(n: number | null): string {
  if (n == null) return "—";
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

export function LiveBrowserViewport({ state }: { state: PriceState }) {
  const { status, source, latestFrame, action, median, count, error } = state;
  const live = status === "streaming";

  return (
    <div className="lbv">
      <div className="lbv-head">
        <span className="lbv-dot-row" aria-hidden="true">
          <span className="lbv-tdot lbv-tdot--r" />
          <span className="lbv-tdot lbv-tdot--y" />
          <span className="lbv-tdot lbv-tdot--g" />
        </span>
        <span className="lbv-title">
          Live price check{source ? ` · ${source}` : ""}
        </span>
        {live && (
          <span className="lbv-live" aria-hidden="true">
            <span className="lbv-live-dot" /> LIVE
          </span>
        )}
        {status === "done" && <span className="lbv-badge">DONE</span>}
      </div>

      {/* The screen: latest screenshot, or a clay scanning skeleton. */}
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

      {/* Action narration + result. */}
      <div className="lbv-foot">
        <span className="lbv-action">
          {error
            ? "Price check unavailable"
            : action || (live ? "Opening marketplace…" : "Queued")}
        </span>
        <span className="lbv-result">
          <span className="lbv-result-median">{fmtUsd(median)}</span>
          <span className="lbv-result-label">
            median{count > 0 ? ` · ${count} listings` : ""}
          </span>
        </span>
      </div>
    </div>
  );
}

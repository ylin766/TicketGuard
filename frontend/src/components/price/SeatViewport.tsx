import { motion, AnimatePresence } from "framer-motion";
import type { PriceState } from "./usePriceStream";
import "./LiveBrowserViewport.css";

/**
 * Seat-view viewport — the seat analogue of LiveBrowserViewport. Instead of the
 * headed browser's screenshots, it plays the seat photos the agent is currently
 * grading inside the same clay frame, so the seat unit mirrors the price unit.
 */

const EASE = [0.22, 1, 0.36, 1] as const;

const API_ORIGIN = "http://localhost:8001";

function resolvePhoto(url: string): string {
  return url.startsWith("http") ? url : `${API_ORIGIN}${url}`;
}

export function SeatViewport({ state }: { state: PriceState }) {
  const { seatSteps, seatImage, listings, status } = state;
  const started = seatSteps.length > 0;
  const done = status === "done";
  const live = started && !done;
  const action = seatSteps.length
    ? seatSteps[seatSteps.length - 1].action
    : "Opening seat library…";
  const graded = listings.filter((l) => l.seat_score != null).length;

  return (
    <div className="lbv">
      <div className="lbv-head">
        <span className="lbv-dot-row" aria-hidden="true">
          <span className="lbv-tdot lbv-tdot--r" />
          <span className="lbv-tdot lbv-tdot--y" />
          <span className="lbv-tdot lbv-tdot--g" />
        </span>
        <span className="lbv-title">Seat views · the agent's eyes</span>
        {live && (
          <span className="lbv-live" aria-hidden="true">
            <span className="lbv-live-dot" /> LIVE
          </span>
        )}
        {done && <span className="lbv-badge">DONE</span>}
      </div>

      <div className="lbv-screen">
        <AnimatePresence mode="popLayout">
          {seatImage ? (
            <motion.img
              key={seatImage}
              className="lbv-frame"
              src={resolvePhoto(seatImage)}
              alt={action}
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
      </div>

      <div className="lbv-foot">
        <span className="lbv-action">{action}</span>
        <span className="lbv-result">
          <span className="lbv-result-median">{graded}</span>
          <span className="lbv-result-label">graded</span>
        </span>
      </div>
    </div>
  );
}

import { motion, AnimatePresence } from "framer-motion";
import type { PriceState } from "./usePriceStream";
import "./PriceActivityPanel.css";

/**
 * The seat flow's "agent activity" — the seat analogue of PriceActivityPanel.
 * Renders the live "seat" step stream (photo match → per-section grading →
 * complete) beside the seat viewport, reusing the price panel's clay timeline
 * styles so the two units read as siblings.
 */

const EASE = [0.22, 1, 0.36, 1] as const;

export function SeatActivityPanel({ state }: { state: PriceState }) {
  const { seatSteps, status } = state;
  const done = status === "done";

  return (
    <div className="pact">
      <div className="pact-head">
        <span className="pact-title">Seat agent</span>
        <span className="pact-sub">match · view · grade</span>
      </div>

      <div className="pact-timeline">
        <AnimatePresence initial={false}>
          {seatSteps.map((s, i) => {
            const isLast = i === seatSteps.length - 1;
            const running = isLast && !done;
            return (
              <motion.div
                key={`${i}-${s.ts}`}
                className="pact-step"
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3, ease: EASE }}
              >
                <span
                  className={`pact-pip${running ? " pact-pip--run" : " pact-pip--ok"}`}
                  aria-hidden="true"
                />
                <span className="pact-step-label">{s.action}</span>
              </motion.div>
            );
          })}
        </AnimatePresence>

        {seatSteps.length === 0 && (
          <div className="pact-step">
            <span className="pact-pip pact-pip--run" aria-hidden="true" />
            <span className="pact-step-label">Opening seat library…</span>
          </div>
        )}
      </div>
    </div>
  );
}

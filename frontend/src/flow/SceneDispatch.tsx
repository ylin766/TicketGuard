import { useEffect } from "react";
import { motion, useReducedMotion } from "framer-motion";
import type { FlowPhase } from "./useFlow";

/**
 * Dispatch transition: the audited URL is shown as a glowing clay "packet" that
 * flies along an arc from the source (left) toward the security pipeline entry
 * (right) — the camera following the data to the next stage. When the flight
 * finishes (plus a minimum dwell so it never flashes by), the flow advances.
 */

const FLIGHT_MS = 1500;

export function SceneDispatch({
  url,
  onDone,
}: {
  url: string;
  onDone: (from: FlowPhase) => void;
}) {
  const reduced = useReducedMotion();

  // Safety net: advance even if the animation's onComplete doesn't fire.
  useEffect(() => {
    const t = window.setTimeout(() => onDone("dispatch"), FLIGHT_MS + 400);
    return () => window.clearTimeout(t);
  }, [onDone]);

  const host = (() => {
    try {
      return new URL(url.startsWith("http") ? url : `https://${url}`).host;
    } catch {
      return url;
    }
  })();

  return (
    <div className="dispatch">
      {/* Source node (left) */}
      <div className="dispatch-node dispatch-node--source">
        <span className="dispatch-node-label">Listing</span>
      </div>

      {/* The dotted route the packet travels */}
      <svg className="dispatch-route" viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden="true">
        <path
          d="M 8 20 Q 50 2 92 20"
          fill="none"
          stroke="currentColor"
          strokeWidth="0.6"
          strokeDasharray="2 2"
        />
      </svg>

      {/* Destination node (right) — the security pipeline entry */}
      <div className="dispatch-node dispatch-node--dest">
        <span className="dispatch-node-label">Security pipeline</span>
      </div>

      {/* The flying URL packet */}
      <motion.div
        className="dispatch-packet clay"
        aria-hidden="true"
        initial={reduced ? { opacity: 0 } : { offsetDistance: "0%", opacity: 0, scale: 0.6 }}
        animate={
          reduced
            ? { opacity: 1 }
            : {
                offsetDistance: "100%",
                opacity: [0, 1, 1, 1, 0.9],
                scale: [0.6, 1, 1, 1, 0.85],
              }
        }
        transition={{ duration: FLIGHT_MS / 1000, ease: [0.4, 0, 0.2, 1] }}
        onAnimationComplete={() => onDone("dispatch")}
        style={{
          // CSS motion-path: follow the same arc as the dotted route.
          offsetPath: "path('M 40 120 Q 480 12 880 120')",
          offsetRotate: "0deg",
        }}
      >
        <span className="dispatch-packet-dot" />
        <span className="dispatch-packet-url">{host}</span>
      </motion.div>
    </div>
  );
}

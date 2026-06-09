import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ThreatIntelPanel } from "../ThreatIntelPanel";
import type { ThreatScanSummary } from "../ThreatIntelPanel";
import { OsintPanel } from "./OsintPanel";
import { useOsintStream } from "./useOsintStream";

/**
 * The security unit's runtime body. The two investigations are a FRONT→BACK
 * workflow that plays out *inside the one unit*, like the input→capsule→parts
 * choreography: only one stage is shown at a time, and the transition between
 * them is animated so the flow reads as a hand-off, not two stacked panels.
 *
 *   stage "scan"     Threat Intelligence runs (13-source scan).
 *   (score gate)     Decisive verdict → finish; grey zone → escalate.
 *   stage "handoff"  Brief bridge: the scan collapses into a one-line verdict
 *                    chip that slides up as the agent stage rises in.
 *   stage "opinion"  Public Opinion Investigation streams its agent trace; the
 *                    verdict chip stays pinned on top as the carried-over result.
 *
 * `onDone` advances the cinematic flow to the report.
 */

// TESTING: force the opinion agent to always run so its trace can be observed.
const FORCE_OSINT = true;

const HIGH_ALERTS = 4;
function isGreyZone(s: ThreatScanSummary): boolean {
  return s.alerts >= 1 && s.alerts < HIGH_ALERTS;
}

const EASE = [0.22, 1, 0.36, 1] as const;

type Stage = "scan" | "opinion";

export function SecurityRuntime({
  url,
  onDone,
}: {
  url: string;
  onDone: () => void;
}) {
  const [stage, setStage] = useState<Stage>("scan");
  const [summary, setSummary] = useState<ThreatScanSummary | null>(null);
  const osint = useOsintStream(url, stage === "opinion", onDone);

  const handleScanDone = (s: ThreatScanSummary) => {
    setSummary(s);
    if (FORCE_OSINT || isGreyZone(s)) {
      setStage("opinion");
    } else {
      onDone();
    }
  };

  return (
    <div className="security-runtime">
      {/* Carried-over verdict chip: appears once the scan finishes and stays
          pinned through the opinion stage — the thread of continuity. */}
      <AnimatePresence>
        {summary && (
          <motion.div
            key="verdict-chip"
            className={`sec-verdict-chip ${summary.flagged ? "sec-verdict-chip--flag" : "sec-verdict-chip--clean"}`}
            initial={{ opacity: 0, y: -8, height: 0 }}
            animate={{ opacity: 1, y: 0, height: "auto" }}
            transition={{ duration: 0.45, ease: EASE }}
          >
            <span className="sec-verdict-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2L4 6v6c0 5.25 3.5 10.15 8 11.35C16.5 22.15 20 17.25 20 12V6L12 2z" />
              </svg>
            </span>
            <span className="sec-verdict-text">
              Threat scan complete · {summary.reported - summary.alerts} clear
              {summary.alerts > 0 ? ` · ${summary.alerts} flagged` : ""}
            </span>
            <span className={`sec-verdict-badge ${summary.flagged ? "sec-verdict-badge--flag" : "sec-verdict-badge--clean"}`}>
              {summary.flagged ? "FLAGGED" : "CLEAN"}
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* A horizontal clay "conveyor": the finished scan is squeezed out to the
          LEFT while the agent stage flows in from the RIGHT and springs open to
          shape — same-space hand-off via motion + clay deformation, no fades.
          Stages share one grid cell; the container clips the off-screen sides. */}
      <div className="sec-stage">
        <AnimatePresence initial={false}>
          {stage === "scan" && (
            <motion.div
              key="scan"
              className="sec-stage-layer"
              initial={{ x: "0%", scaleX: 1, scaleY: 1 }}
              animate={{ x: "0%", scaleX: 1, scaleY: 1 }}
              exit={{
                x: "-110%",
                scaleX: 0.78,
                scaleY: 0.9,
                transition: { type: "spring", stiffness: 120, damping: 20, mass: 1 },
              }}
            >
              <ThreatIntelPanel url={url} variant="runtime" onDone={handleScanDone} />
            </motion.div>
          )}
          {stage === "opinion" && (
            <motion.div
              key="opinion"
              className="sec-stage-layer"
              // Enters from the right, then springs its scaleX open like clay
              // being poured into the mould and settling to shape.
              initial={{ x: "110%", scaleX: 1.12, scaleY: 0.94 }}
              animate={{
                x: "0%",
                scaleX: 1,
                scaleY: 1,
                transition: { type: "spring", stiffness: 110, damping: 16, mass: 1, delay: 0.08 },
              }}
            >
              <OsintPanel state={osint} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

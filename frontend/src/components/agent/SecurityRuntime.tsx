import { useState, useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ThreatIntelPanel } from "../ThreatIntelPanel";
import type { ThreatScanSummary, ThreatScanCache } from "../ThreatIntelPanel";
import { AgentPanel } from "./AgentPanel";
import { useAgentStream, type AgentState } from "./useAgentStream";
import { AgentBrowserViewport } from "./AgentBrowserViewport";
import { useBrowserCheckStream } from "./useBrowserCheckStream";

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

// Set to `true` only while debugging to force the opinion agent to always run
// so its trace can be observed. Production gates it on the grey zone.
const FORCE_AGENT = false;

const HIGH_ALERTS = 4;
function isGreyZone(s: ThreatScanSummary): boolean {
  return s.alerts >= 1 && s.alerts < HIGH_ALERTS;
}


type Stage = "scan" | "opinion";

export function SecurityRuntime({
  url,
  onDone,
  onScanComplete,
  onAgentComplete,
}: {
  url: string;
  onDone: () => void;
  onScanComplete?: (cache: ThreatScanCache) => void;
  onAgentComplete?: (state: AgentState) => void;
}) {
  const [stage, setStage] = useState<Stage>("scan");
  const agent = useAgentStream(url, stage === "opinion");
  // Layer-2 browser probe runs alongside the OSINT opinion agent in the grey
  // zone, streaming the headed browser's exploration into the clay viewport.
  const browser = useBrowserCheckStream(url, stage === "opinion");

  useEffect(() => {
    if (agent.status === "done" || agent.status === "error") {
      onAgentComplete?.(agent);
      onDone();
    }
  }, [agent.status, agent, onAgentComplete, onDone]);

  const handleScanDone = (_s: ThreatScanSummary) => {
    if (FORCE_AGENT || isGreyZone(_s)) {
      setStage("opinion");
    } else {
      onDone();
    }
  };

  const handleScanComplete = (sources: import("../../types").ThreatSource[], flagged: boolean) => {
    onScanComplete?.({ sources, flagged });
  };

  return (
    <div className="security-runtime">

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
              <ThreatIntelPanel
                url={url}
                variant="runtime"
                onDone={handleScanDone}
                onComplete={handleScanComplete}
              />
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
              <div className="sec-opinion-stack">
                <AgentBrowserViewport state={browser} />
                <AgentPanel state={agent} variant="runtime" />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

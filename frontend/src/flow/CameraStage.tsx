import { type ReactNode } from "react";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { DataFlow } from "./DataFlow";
import type { ThreatScanCache } from "../components/ThreatIntelPanel";
import type { PriceState } from "../components/price/usePriceStream";
import type { FlowPhase, FlowState } from "./useFlow";

/**
 * Orchestrates the continuous flow inside a fixed viewport:
 *   input screen  →  [DataFlow: one carrier travelling dispatch→…→settle]  →  report
 *
 * The input card and the data carrier share a `layoutId`, so when the audit
 * starts the whole card MORPHS into the travelling pill (its contents crossfade
 * out as the pill fades in along the same box). LayoutGroup + a non-"wait"
 * AnimatePresence keep that shared-element morph continuous across the swap.
 */

const MIDDLE: FlowPhase[] = ["dispatch", "split", "pipeline"];

export function CameraStage({
  flow,
  input,
  report,
  onScanComplete,
  agentState,
  browserState,
  price,
  reportReady,
}: {
  flow: FlowState;
  input: ReactNode;
  report: ReactNode;
  onScanComplete?: (cache: ThreatScanCache) => void;
  agentState: import("../components/agent/useAgentStream").AgentState;
  browserState: import("../components/agent/useBrowserCheckStream").BrowserCheckState;
  price?: PriceState;
  reportReady?: boolean;
}) {
  const { phase, url } = flow;
  const inMiddle = MIDDLE.includes(phase);

  return (
    <div className="camera-stage">
      <LayoutGroup>
        <AnimatePresence>
          {phase === "input" && (
            <motion.div
              key="input"
              className="flow-scene flow-scene--input"
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              /* No opacity on exit: the input card morphs (via shared layoutId)
                 into the carrier, so it must stay visible while it transforms.
                 Surrounding chrome (logo/trust row) simply unmounts. */
              exit={{ transition: { duration: 0 } }}
              transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
            >
              {input}
            </motion.div>
          )}

          {inMiddle && (
            <motion.div
              key="dataflow"
              className="flow-scene flow-scene--flow"
              /* The carrier itself is the shared-layout element; don't fade the
                 wrapper or it would hide the morph. */
              initial={false}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, transition: { duration: 0.3 } }}
            >
              <DataFlow
                flow={flow}
                url={url ?? ""}
                onScanComplete={onScanComplete}
                agentState={agentState}
                browserState={browserState}
                price={price}
                reportReady={reportReady}
              />
            </motion.div>
          )}

          {phase === "report" && (
            <motion.div
              key="report"
              className="flow-scene flow-scene--report"
              initial={{ opacity: 0, y: 24, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            >
              {report}
            </motion.div>
          )}
        </AnimatePresence>
      </LayoutGroup>
    </div>
  );
}

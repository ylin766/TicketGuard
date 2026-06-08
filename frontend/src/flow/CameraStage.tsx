import { useEffect, type ReactNode } from "react";
import { AnimatePresence } from "framer-motion";
import { Scene } from "./Scene";
import { SceneDispatch } from "./SceneDispatch";
import type { FlowPhase, FlowState } from "./useFlow";

/**
 * The fixed-viewport "camera". It renders exactly one scene for the current
 * phase and lets AnimatePresence play the directional enter/exit (the camera
 * pan). The background (grass + balls) lives elsewhere and stays put.
 *
 * For now `pipeline` / `agent` / `settle` are placeholder beats that auto-
 * advance; they'll be filled in by later steps. `input` and `report` are passed
 * in so this component stays decoupled from their data.
 */

const PLACEHOLDER_MS: Partial<Record<FlowPhase, number>> = {
  pipeline: 1600,
  agent: 1600,
  settle: 700,
};

const PLACEHOLDER_LABEL: Partial<Record<FlowPhase, string>> = {
  pipeline: "Collecting threat intelligence…",
  agent: "Agent investigating…",
  settle: "Compiling report…",
};

function PlaceholderScene({
  phase,
  onDone,
}: {
  phase: FlowPhase;
  onDone: (from: FlowPhase) => void;
}) {
  useEffect(() => {
    const ms = PLACEHOLDER_MS[phase] ?? 1200;
    const t = window.setTimeout(() => onDone(phase), ms);
    return () => window.clearTimeout(t);
  }, [phase, onDone]);

  return (
    <div className="flow-placeholder">
      <span className="flow-placeholder-dot" aria-hidden="true" />
      <span className="flow-placeholder-label">{PLACEHOLDER_LABEL[phase]}</span>
    </div>
  );
}

export function CameraStage({
  flow,
  input,
  report,
}: {
  flow: FlowState;
  input: ReactNode;
  report: ReactNode;
}) {
  const { phase, url, advance } = flow;

  let body: ReactNode;
  let className = "";
  switch (phase) {
    case "input":
      body = input;
      className = "flow-scene--input";
      break;
    case "dispatch":
      body = <SceneDispatch url={url ?? ""} onDone={advance} />;
      className = "flow-scene--dispatch";
      break;
    case "report":
      body = report;
      className = "flow-scene--report";
      break;
    default:
      body = <PlaceholderScene phase={phase} onDone={advance} />;
      className = `flow-scene--${phase}`;
  }

  return (
    <div className="camera-stage">
      <AnimatePresence mode="wait">
        <Scene key={phase} className={className}>
          {body}
        </Scene>
      </AnimatePresence>
    </div>
  );
}

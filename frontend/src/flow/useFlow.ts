import { useCallback, useEffect, useRef, useState } from "react";

/** Local prefers-reduced-motion hook (read at render time so it's testable;
 *  framer's useReducedMotion is a module-level singleton that's hard to mock). */
function usePrefersReducedMotion(): boolean {
  const query = "(prefers-reduced-motion: reduce)";
  const [reduced, setReduced] = useState(
    () =>
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia(query).matches,
  );
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia(query);
    const onChange = () => setReduced(mql.matches);
    mql.addEventListener?.("change", onChange);
    return () => mql.removeEventListener?.("change", onChange);
  }, []);
  return reduced;
}

/**
 * The cinematic audit flow is an auto-advancing state machine (no manual
 * Next/Skip — it's a narrated experience). Each phase plays, signals it's done,
 * and the machine advances on its own:
 *
 *   input → dispatch → pipeline → agent → settle → report
 *
 * - `input`    waits for the user to start an audit (the only manual trigger).
 * - `dispatch` / `handoff-ish` / `settle` are pure front-end transition beats
 *   advanced by their animation's onComplete (with a minimum dwell so nothing
 *   flashes by).
 * - `pipeline` is a *real* wait: it advances when the threat-intel SSE finishes.
 * - `agent` is timed choreography for now (no backend yet).
 *
 * Reduced motion is an accessibility requirement (not a skip feature): it jumps
 * straight to `report` once an audit starts.
 */
export type FlowPhase =
  | "input"
  | "dispatch"
  | "pipeline"
  | "agent"
  | "settle"
  | "report";

/** Linear order of phases; advancing always goes to the next one. */
export const FLOW_ORDER: FlowPhase[] = [
  "input",
  "dispatch",
  "pipeline",
  "agent",
  "settle",
  "report",
];

export interface FlowState {
  phase: FlowPhase;
  /** The URL being audited (set when the flow starts). */
  url: string | null;
  /** True once an audit has been started from the input screen. */
  started: boolean;
  /** Begin the flow with a URL (called from the input scene). */
  start: (url: string) => void;
  /** Advance from the current phase to the next (called by a phase when done). */
  advance: (from: FlowPhase) => void;
  /** Reset back to the input screen. */
  reset: () => void;
}

function nextPhase(phase: FlowPhase): FlowPhase {
  const i = FLOW_ORDER.indexOf(phase);
  if (i < 0 || i === FLOW_ORDER.length - 1) return phase;
  return FLOW_ORDER[i + 1];
}

export function useFlow(): FlowState {
  const [phase, setPhase] = useState<FlowPhase>("input");
  const [url, setUrl] = useState<string | null>(null);
  const [started, setStarted] = useState(false);
  const reducedMotion = usePrefersReducedMotion();
  // Guard against double-advance: a phase may only advance once per visit.
  const phaseRef = useRef<FlowPhase>("input");
  phaseRef.current = phase;

  const start = useCallback(
    (nextUrl: string) => {
      setUrl(nextUrl);
      setStarted(true);
      // Reduced motion: skip the cinematics, go straight to the report.
      setPhase(reducedMotion ? "report" : "dispatch");
    },
    [reducedMotion],
  );

  const advance = useCallback((from: FlowPhase) => {
    // Only advance if the caller is reporting completion of the *current* phase,
    // so a stale onComplete can't skip ahead.
    if (phaseRef.current !== from) return;
    setPhase((p) => nextPhase(p));
  }, []);

  const reset = useCallback(() => {
    setUrl(null);
    setStarted(false);
    setPhase("input");
  }, []);

  // If the user's motion preference flips to reduced mid-flight, settle on report.
  useEffect(() => {
    if (reducedMotion && started && phase !== "input" && phase !== "report") {
      setPhase("report");
    }
  }, [reducedMotion, started, phase]);

  return { phase, url, started, start, advance, reset };
}

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
 *   input → dispatch → split → pipeline → report
 *
 * - `input`    waits for the user to start an audit (the only manual trigger).
 * - `dispatch` is a pure front-end beat: the URL capsule.
 * - `split`    is a beat: the capsule slides left, melts, and its substance is
 *   divided into three processing units (security / price / seat).
 * - `pipeline` is a *real* wait: it advances when the threat-intel SSE finishes.
 *   (price / seat are placeholders for now.)
 *
 * Reduced motion is an accessibility requirement (not a skip feature): it jumps
 * straight to `report` once an audit starts.
 */
export type FlowPhase =
  | "input"
  | "dispatch"
  | "split"
  | "pipeline"
  | "report";

/** Linear order of phases; advancing always goes to the next one. */
export const FLOW_ORDER: FlowPhase[] = [
  "input",
  "dispatch",
  "split",
  "pipeline",
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
      // Reduced motion skips the purely decorative beats (dispatch / split) but
      // still enters the pipeline: that's where the real audit work runs (the
      // threat scan + opinion agent), and the report is assembled from its
      // results — so we can't skip past it without losing the data.
      setPhase(reducedMotion ? "pipeline" : "dispatch");
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

  // If the user's motion preference flips to reduced mid-flight, collapse the
  // decorative beats (dispatch / split) into the pipeline — but never skip the
  // pipeline itself (the audit data is gathered there).
  useEffect(() => {
    if (reducedMotion && started && (phase === "dispatch" || phase === "split")) {
      setPhase("pipeline");
    }
  }, [reducedMotion, started, phase]);

  return { phase, url, started, start, advance, reset };
}

import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ProcessUnits } from "./ProcessUnits";
import type { FlowState } from "./useFlow";

/**
 * Clay-liquid "split & pour" flow (16:9 friendly):
 *
 *   dispatch  the URL capsule (morphed from the input card) settles at the
 *             CENTRE of the stage and holds for a beat.
 *   split     the capsule glides to the far LEFT and melts into a blob of clay
 *             liquid. The blob stretches and pinches off into THREE clay
 *             streams (gooey filter — overlapping metaballs that merge then
 *             separate, like real liquid). As each stream reaches a unit, that
 *             unit's clay body is "poured" full from the injection side
 *             (clip-path fill) and its content rises in with the clay.
 *   pipeline  the clay liquid is spent; the three filled units glide to centre
 *             and the security unit streams the real threat-intel feed.
 *
 * Technique: gooey SVG filter (Lucas Bebber / Codrops "Creative Gooey
 * Effects"). The metaballs only merge while they OVERLAP, so the streams start
 * stacked on the source blob and fan out — giving a true liquid split rather
 * than separate dots. No thin SVG strokes anywhere; every moving mass is clay.
 */

const DISPATCH_MS = 850;
const SPLIT_MS = 2200;
const EASE = [0.22, 1, 0.36, 1] as const;
const EASE_OUT = [0.16, 1, 0.3, 1] as const;

function shortHost(url: string): string {
  try {
    return new URL(url.startsWith("http") ? url : `https://${url}`).host;
  } catch {
    return url;
  }
}

/** Hidden SVG filter that fuses overlapping clay blobs into one liquid mass. */
function GooDefs() {
  return (
    <svg className="goo-defs" aria-hidden="true">
      <defs>
        <filter id="flow-goo">
          <feGaussianBlur in="SourceGraphic" stdDeviation="9" result="blur" />
          <feColorMatrix
            in="blur"
            mode="matrix"
            values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 19 -8"
            result="goo"
          />
          <feComposite in="SourceGraphic" in2="goo" operator="atop" />
        </filter>
      </defs>
    </svg>
  );
}

/** The clay liquid: a source mass that feeds three chains of droplets. The
 *  chains share a common trunk (left -> the split node), then peel off along
 *  smooth curves to the LEFT EDGE of each unit — never straight to the centre.
 */
function MeltGoo() {
  // x positions (% of stage): source -> split node -> mid control -> unit edge.
  const SRC_X = 9;
  const NODE_X = 30;
  const END_X = 42;
  const MID_X = (NODE_X + END_X) / 2;

  // Each stream ends at a different branch height; the middle one stays level.
  const streams = [
    { top: 18, delay: 0.16 },
    { top: 50, delay: 0.1 },
    { top: 82, delay: 0.16 },
  ];
  const BEADS = 5;

  return (
    <motion.div
      className="melt-goo"
      aria-hidden="true"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25, ease: EASE_OUT }}
    >
      {/* Source mass — pools where the capsule melted, then feeds the streams.
          It grows large and FAST so it fully covers the shrinking capsule
          before the capsule fades: same clay colour + full overlap = a seamless
          handoff (one substance), not a crossfade between two components. */}
      <motion.span
        className="melt-blob melt-source"
        initial={{ left: `${SRC_X}%`, top: "50%", scale: 0.5 }}
        animate={{ left: `${SRC_X}%`, top: "50%", scale: [0.5, 1.25, 1.05, 0.85] }}
        transition={{ duration: SPLIT_MS / 1000, ease: EASE_OUT, times: [0, 0.22, 0.55, 1] }}
      />
      {streams.map((s, si) => {
        // Path keyframes: trunk (level) -> node -> curved branch -> unit edge.
        const leftKf = [`${SRC_X}%`, `${NODE_X}%`, `${MID_X}%`, `${END_X}%`];
        const midTop = (50 + s.top) / 2;
        const topKf = ["50%", "50%", `${midTop}%`, `${s.top}%`];
        return Array.from({ length: BEADS }).map((_, bi) => {
          const t = bi / (BEADS - 1); // 0..1 position in the chain
          return (
            <motion.span
              key={`${si}-${bi}`}
              className="melt-blob melt-bead"
              initial={{ left: `${SRC_X}%`, top: "50%", scale: 0 }}
              animate={{
                left: leftKf,
                top: topKf,
                // bead shrinks to nothing at the unit edge — absorbed into the
                // mould as the water-level fill begins (continuous pour).
                scale: [0, 0.95, 0.8, 0.15],
              }}
              transition={{
                duration: 1.0,
                // beads start only after the capsule has melted into the source,
                // and later beads leave later -> one travelling chain of clay.
                delay: 0.4 + s.delay + t * 0.5,
                ease: EASE_OUT,
                times: [0, 0.4, 0.75, 1],
              }}
            />
          );
        });
      })}
    </motion.div>
  );
}

export function DataFlow({ flow, url }: { flow: FlowState; url: string }) {
  const { phase, advance } = flow;
  const host = shortHost(url);

  const splitting = phase === "dispatch" || phase === "split";
  const gooActive = phase === "split";

  // Timed beats auto-advance; pipeline waits for the threat-intel stream.
  useEffect(() => {
    let ms: number | null = null;
    if (phase === "dispatch") ms = DISPATCH_MS;
    else if (phase === "split") ms = SPLIT_MS;
    if (ms === null) return;
    const t = window.setTimeout(() => advance(phase), ms);
    return () => window.clearTimeout(t);
  }, [phase, advance]);

  return (
    <div className={`dataflow ${splitting ? "dataflow--split" : "dataflow--center"}`}>
      <GooDefs />

      {/* The capsule: morphs in at centre, glides left, then melts into clay. */}
      <AnimatePresence>
        {splitting && (
          <motion.div
            key="capsule"
            layoutId="data-carrier"
            className="data-carrier split-capsule"
            style={{ borderRadius: 999 }}
            initial={false}
            animate={{
              left: gooActive ? "9%" : "44%",
              // Squash into the source blob; stays fully opaque until it is
              // small enough to be hidden inside the (same-colour) blob, then
              // cuts — so there is no visible crossfade, only a melt.
              scaleX: gooActive ? [1, 1, 1.1, 0.2] : 1,
              scaleY: gooActive ? [1, 1, 0.5, 0.2] : 1,
              opacity: gooActive ? [1, 1, 1, 0] : 1,
            }}
            transition={{
              left: { duration: 0.55, ease: EASE_OUT },
              scaleX: { duration: SPLIT_MS / 1000, ease: EASE_OUT, times: [0, 0.18, 0.32, 0.46] },
              scaleY: { duration: SPLIT_MS / 1000, ease: EASE_OUT, times: [0, 0.18, 0.32, 0.46] },
              opacity: { duration: SPLIT_MS / 1000, times: [0, 0.32, 0.42, 0.48] },
            }}
          >
            <div className="carrier-pill">
              <span className="carrier-dot" aria-hidden="true" />
              <span className="carrier-url">{host}</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Clay liquid splitting into three streams. */}
      <AnimatePresence>{gooActive && <MeltGoo />}</AnimatePresence>

      {/* The three units: right-of-centre while pouring, then glide to centre. */}
      <motion.div
        className={`units-zone ${splitting ? "units-zone--right" : "units-zone--center"}`}
        layout
        transition={{ layout: { duration: 0.8, ease: EASE } }}
      >
        <ProcessUnits
          phase={phase}
          url={url}
          onSecurityDone={() => advance("pipeline")}
        />
      </motion.div>
    </div>
  );
}

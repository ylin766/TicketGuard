import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ProcessUnits } from "./ProcessUnits";
import type { ThreatScanCache } from "../components/ThreatIntelPanel";
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

const DISPATCH_MS = 650; // capsule morphs in at centre and holds a beat
const SPLIT_MS = 2400; // glide-left (~0–0.3) then melt + droplet streams fit inside
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
        {/* sRGB interpolation (not the default linearRGB) is markedly cheaper to
            rasterize each frame, so the live blob merge stays smooth. */}
        <filter id="flow-goo" colorInterpolationFilters="sRGB">
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

/**
 * The clay droplet streams. There is NO separate source ball: the beads emerge
 * directly from the capsule's melt point and, because they share the SAME gooey
 * filter container as the capsule, they stick and stretch off it like one
 * substance pulling apart. Three chains share a common trunk along the centre
 * line, then peel off along smooth curves to each unit's LEFT EDGE.
 */
const SRC_X = 12; // where the capsule melts (matches the capsule's split x)
const NODE_X = 30; // the split node — trunk ends, branches begin
const END_X = 45; // the units' left edge (matches .units-zone--right margin-left)

/** Cubic-bezier point (all values in stage %). */
function cubic(
  p0: [number, number],
  c1: [number, number],
  c2: [number, number],
  p3: [number, number],
  t: number
): [number, number] {
  const u = 1 - t;
  const a = u * u * u;
  const b = 3 * u * u * t;
  const c = 3 * u * t * t;
  const d = t * t * t;
  return [
    a * p0[0] + b * c1[0] + c * c2[0] + d * p3[0],
    a * p0[1] + b * c1[1] + c * c2[1] + d * p3[1],
  ];
}

/**
 * Build one stream's path as a dense set of {left%, top%} keyframes that move
 * at CONSTANT speed (times spaced by cumulative arc length, ease: linear):
 *   1. a straight trunk along the centre line (SRC_X -> NODE_X, top 50)
 *   2. a smooth cubic branch (NODE_X -> END_X) whose control points are
 *      horizontal at BOTH ends, so it leaves the node horizontally and arrives
 *      at the unit horizontally — the S-curve in the user's sketch.
 */
function buildStreamPath(targetTopOffset: number) {
  const pts: [number, number][] = [];
  // Trunk — a couple of points keep it dead straight along the centre axis (y=0).
  pts.push([SRC_X, 0]);
  pts.push([NODE_X, 0]);
  // Branch — sample the cubic. Horizontal handles (same y as their anchor).
  const p0: [number, number] = [NODE_X, 0];
  const p3: [number, number] = [END_X, targetTopOffset];
  const handle = (END_X - NODE_X) * 0.6;
  const c1: [number, number] = [NODE_X + handle, 0];
  const c2: [number, number] = [END_X - handle, targetTopOffset];
  const SEGMENTS = 14;
  for (let i = 1; i <= SEGMENTS; i++) {
    pts.push(cubic(p0, c1, c2, p3, i / SEGMENTS));
  }
  // Cumulative arc length -> normalized times for constant speed.
  const times: number[] = [0];
  let total = 0;
  for (let i = 1; i < pts.length; i++) {
    const dx = pts[i][0] - pts[i - 1][0];
    const dy = pts[i][1] - pts[i - 1][1];
    total += Math.hypot(dx, dy);
    times.push(total);
  }
  for (let i = 0; i < times.length; i++) times[i] /= total;
  return {
    left: pts.map((p) => `${p[0]}%`),
    top: pts.map((p) => `calc(50% + ${p[1]}px)`),
    times,
  };
}

function MeltBeads() {
  // Each stream ends at a precise pixel offset from the vertical centre.
  // The units are 132px high with 18px gaps -> exactly 150px between centres.
  const streams = [
    { topOffset: -150, delay: 0.12 },
    { topOffset: 0, delay: 0.06 },
    { topOffset: 150, delay: 0.12 },
  ];
  const BEADS = 6;
  // When the first bead of a stream reaches the unit edge (≈ travel start +
  // duration), a clay "splash" blooms there: under the gooey filter it reads as
  // the liquid pooling at the mould edge and being absorbed as the fill begins.
  const SPLASH_AT = (sDelay: number) => 0.72 + sDelay + 1.05;

  return (
    <>
      {streams.map((s, si) => {
        const path = buildStreamPath(s.topOffset);
        // Scale keyframes sampled at the same count as the path so the bead
        // swells out of the capsule then thins as it is absorbed at the unit.
        const scaleKf = path.times.map((tt) =>
          tt < 0.12 ? tt / 0.12 : tt > 0.85 ? 0.85 - (tt - 0.85) * 4.6 : 1
        );
        return (
          <span key={si}>
            {Array.from({ length: BEADS }).map((_, bi) => {
              const t = bi / (BEADS - 1); // 0..1 position in the chain
              return (
                <motion.span
                  key={`${si}-${bi}`}
                  className="melt-blob melt-bead"
                  // Every bead is born AT the capsule's melt point, overlapping
                  // it, so the gooey filter welds them into the capsule.
                  initial={{ left: `${SRC_X}%`, top: "calc(50% + 0px)", scale: 0 }}
                  animate={{
                    left: path.left,
                    top: path.top,
                    scale: scaleKf,
                  }}
                  transition={{
                    duration: 1.05,
                    // beads start pulling out only once the capsule has glided
                    // to the source point and begins to melt (~0.72s); later
                    // beads leave later -> one continuous travelling stream.
                    delay: 0.72 + s.delay + t * 0.5,
                    // LINEAR motion + arc-length-spaced times = constant speed
                    // straight through the split node (no pause), along a curve.
                    ease: "linear",
                    times: path.times,
                  }}
                />
              );
            })}
            {/* Injection splash at the unit edge — pools, spreads and is absorbed. */}
            <motion.span
              className="melt-blob melt-splash"
              style={{ left: `${END_X}%`, top: `calc(50% + ${s.topOffset}px)` }}
              initial={{ scale: 0, opacity: 0 }}
              animate={{
                scale: [0, 1.15, 1.4, 0.6],
                opacity: [0, 1, 1, 0],
              }}
              transition={{
                duration: 0.9,
                delay: SPLASH_AT(s.delay),
                ease: EASE_OUT,
                times: [0, 0.35, 0.7, 1],
              }}
            />
          </span>
        );
      })}
    </>
  );
}

export function DataFlow({
  flow,
  url,
  onScanComplete,
  onAgentComplete,
  price,
}: {
  flow: FlowState;
  url: string;
  onScanComplete?: (cache: ThreatScanCache) => void;
  onAgentComplete?: (state: import("../components/agent/useAgentStream").AgentState) => void;
  price?: import("../components/price/usePriceStream").PriceState;
}) {
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

      {/* Capsule + droplets live in ONE gooey-filtered stage, so the beads
          weld onto the capsule and pull off it like a single clay mass. The
          filter is only enabled during the split (so the capsule's text stays
          crisp while it morphs in during dispatch). */}
      <div className={`melt-stage ${gooActive ? "melt-stage--goo" : ""}`}>
        <AnimatePresence>
          {splitting && (
            <motion.div
              key="capsule"
              layoutId="data-carrier"
              className="data-carrier split-capsule"
              style={{ borderRadius: 999 }}
              initial={false}
              // Vertical centring (translateY -50%) is prepended to whatever
              // transform Framer generates (the layout-morph projection + the
              // animated scale), so the capsule stays on the stage's mid-line
              // for any height — unlike a fixed margin — without breaking the
              // shared-element morph.
              transformTemplate={(_latest, generated) =>
                `translateY(-50%) ${generated}`
              }
              animate={{
                // ONE synced timeline: first the capsule glides to the source
                // point (scale held at 1), and only AFTER it arrives does it
                // squash and melt to nothing — so it never shrinks mid-flight
                // and always vanishes at the correct left position.
                left: gooActive
                  ? ["44%", `${SRC_X}%`, `${SRC_X}%`, `${SRC_X}%`]
                  : "44%",
                scaleX: gooActive ? [1, 1, 1.12, 0.5, 0] : 1,
                scaleY: gooActive ? [1, 1, 0.82, 0.42, 0] : 1,
              }}
              transition={{
                // Shared-element morph (input card -> capsule) keeps its spring.
                layout: { type: "spring", stiffness: 110, damping: 16, mass: 1 },
                // Glide + melt share the SAME tween timeline (no spring) so the
                // keyframe times stay in lock-step: 0–0.3 glide, then melt.
                left: {
                  duration: SPLIT_MS / 1000,
                  ease: EASE_OUT,
                  times: [0, 0.3, 0.6, 1],
                },
                scaleX: {
                  duration: SPLIT_MS / 1000,
                  ease: EASE_OUT,
                  times: [0, 0.3, 0.42, 0.55, 0.62],
                },
                scaleY: {
                  duration: SPLIT_MS / 1000,
                  ease: EASE_OUT,
                  times: [0, 0.3, 0.42, 0.55, 0.62],
                },
              }}
            >
              {/* The label stays crisp while the capsule glides, then fades as
                  the body begins to squash/melt — not an instant cut. */}
              <motion.div
                className="carrier-pill"
                initial={false}
                animate={{
                  opacity: gooActive ? [1, 1, 0] : 1,
                  scale: gooActive ? [1, 1, 0.85] : 1,
                }}
                transition={{
                  duration: gooActive ? SPLIT_MS / 1000 : 0.3,
                  ease: EASE_OUT,
                  // hold during the glide (0–0.3), fade out across the melt.
                  times: gooActive ? [0, 0.3, 0.6] : undefined,
                }}
              >
                <span className="carrier-dot" aria-hidden="true" />
                <span className="carrier-url">{host}</span>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* The droplet streams pulling off the melting capsule. */}
        {gooActive && <MeltBeads />}
      </div>

      {/* The three units: right-of-centre while pouring, then glide to centre. */}
      <motion.div
        className={`units-zone ${splitting ? "units-zone--right" : "units-zone--center"}`}
        layout
        transition={{ layout: { type: "spring", stiffness: 120, damping: 18, mass: 1 } }}
      >
        <ProcessUnits
          phase={phase}
          url={url}
          onSecurityDone={() => advance("pipeline")}
          onScanComplete={onScanComplete}
          onAgentComplete={onAgentComplete}
          price={price}
        />
      </motion.div>
    </div>
  );
}

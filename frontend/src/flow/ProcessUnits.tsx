import { motion } from "framer-motion";
import { SecurityRuntime } from "../components/agent/SecurityRuntime";
import type { ThreatScanCache } from "../components/ThreatIntelPanel";
import type { FlowPhase } from "./useFlow";

/**
 * The three processing units the data is split into. Only `security` is wired
 * up (its process card morphs into the ThreatIntelPanel); `price` and `seat`
 * are placeholders ("coming soon") that hold their column. Strictly three equal
 * columns (16:9 friendly); each unit is responsive and never needs its own
 * scrollbar — content adapts to the column.
 */

const EASE = [0.22, 1, 0.36, 1] as const;

function IconShield() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 2L4 6v6c0 5.25 3.5 10.15 8 11.35C16.5 22.15 20 17.25 20 12V6L12 2z" />
    </svg>
  );
}
function IconCoin() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v10M9.5 9.5h4a1.8 1.8 0 0 1 0 3.6h-3a1.8 1.8 0 0 0 0 3.6h4" />
    </svg>
  );
}
function IconSeat() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 11V6a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v5M4 11h16v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-4zM7 17v3M17 17v3" />
    </svg>
  );
}

interface UnitDef {
  key: "security" | "price" | "seat";
  title: string;
  sub: string;
  icon: () => JSX.Element;
}

const UNITS: UnitDef[] = [
  { key: "security", title: "Threat Intelligence", sub: "13 sources across the web", icon: IconShield },
  { key: "price", title: "Price Analysis", sub: "Live market comparison", icon: IconCoin },
  { key: "seat", title: "Seat & Sightline", sub: "Obstruction & view check", icon: IconSeat },
];

export function ProcessUnits({
  phase,
  url,
  onSecurityDone,
  onScanComplete,
  onAgentComplete,
}: {
  phase: FlowPhase;
  url: string;
  onSecurityDone: () => void;
  onScanComplete?: (cache: ThreatScanCache) => void;
  onAgentComplete?: (state: import("../components/agent/useAgentStream").AgentState) => void;
}) {
  const isPipeline = phase === "pipeline";
  // The clay is poured into each unit once the stream reaches it.
  const filled = phase === "split" || isPipeline;
  // Water-level fill: clip from the TOP edge downward (top inset 100% -> 0%),
  // so the clay surface rises until the mould is full.
  const fillEmpty = "inset(100% 0 0 0 round 24px)";
  const fillFull = "inset(0% 0 0 0 round 24px)";
  // Fills begin the moment that unit's clay stream ARRIVES at its edge (matching
  // the bead travel + splash in DataFlow: ≈0.72 glide + 1.05 travel), so the
  // pour is continuous. Each mould then fills at its own pace (durations vary)
  // so the three top out at slightly different times.
  const fillDelay = [1.85, 1.78, 1.85];
  const fillDur = [0.7, 0.95, 1.2];

  return (
    <div className="process-units">
      {UNITS.map((u, i) => {
        const active = u.key === "security";
        // The security unit in the pipeline shows the panel's own header, so
        // suppress the unit head to avoid a duplicated title row.
        const showHead = !(active && isPipeline);
        return (
          <motion.div
            key={u.key}
            className={`punit ${active ? "punit--active" : "punit--soon"} punit--${u.key}`}
            // The whole unit (its empty clay mould included) stays invisible
            // until that stream's droplet reaches its edge, then reveals as ONE
            // piece. No `layout` and no scale here: nested layout projection +
            // a scale spring were fighting each other (the stutter) and made the
            // content pop before its frame. A single opacity+y spring is smooth.
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: filled ? 1 : 0, y: filled ? 0 : 10 }}
            transition={{
              delay: filled ? fillDelay[i] : 0,
              opacity: { duration: 0.35, ease: EASE },
              y: { type: "spring", stiffness: 220, damping: 22, mass: 0.9 },
            }}
          >
            {/* The clay body poured into the mould, rising like a water level
                from the bottom until full — this IS the visible frame, so it
                leads; the content surfaces just behind it. */}
            <motion.div
              className="punit-fill"
              initial={{ clipPath: fillEmpty }}
              animate={{ clipPath: filled ? fillFull : fillEmpty }}
              transition={{ duration: fillDur[i], delay: fillDelay[i] + 0.1, ease: EASE }}
            />

            {/* Content surfaces with the rising clay, a beat after the fill. */}
            <motion.div
              className="punit-content"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: filled ? 1 : 0, y: filled ? 0 : 10 }}
              transition={{ duration: 0.5, delay: fillDelay[i] + fillDur[i] * 0.5, ease: EASE }}
            >
              {showHead && (
                <div className="punit-head">
                  <span className="punit-icon" aria-hidden="true">
                    <u.icon />
                  </span>
                  <div className="punit-titles">
                    <h3 className="punit-title">{u.title}</h3>
                    <span className="punit-sub">{u.sub}</span>
                  </div>
                </div>
              )}

              <motion.div className="punit-body" layout>
                {active ? (
                  isPipeline ? (
                    <SecurityRuntime
                      url={url}
                      onDone={onSecurityDone}
                      onScanComplete={onScanComplete}
                      onAgentComplete={onAgentComplete}
                    />
                  ) : (
                    <div className="punit-process">
                      <span className="punit-process-dot" aria-hidden="true" />
                      <span className="punit-process-label">Initialising scan…</span>
                    </div>
                  )
                ) : (
                  <div className="punit-soon-body">
                    <span className="punit-soon-tag">Coming soon</span>
                  </div>
                )}
              </motion.div>
            </motion.div>
          </motion.div>
        );
      })}
    </div>
  );
}

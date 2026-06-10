import { motion, AnimatePresence } from "framer-motion";
import type { PriceState } from "./usePriceStream";
import "./PriceActivityPanel.css";

/**
 * The price flow's "agent activity" — a live step timeline beside the browser
 * viewport, mirroring the security column's AgentPanel so the price column also
 * shows what its agent is *doing*: the scraper's per-step actions, then the two
 * Gemini calls (vision extraction of the buyer's ticket + market evaluation),
 * ending on the verdict. Price isn't a multi-step ReAct agent, so this renders
 * the SSE frame sequence rather than tool-call nodes.
 */

const EASE = [0.22, 1, 0.36, 1] as const;

function fmtMoney(n: number | null | undefined, currency = "USD"): string {
  if (n == null) return "—";
  try {
    return n.toLocaleString("en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    });
  } catch {
    return `${n.toLocaleString("en-US", { maximumFractionDigits: 0 })} ${currency}`;
  }
}

const VERDICT_LABEL: Record<string, string> = {
  good_deal: "Good deal",
  fair: "Fair price",
  slightly_high: "A bit high",
  overpriced: "Overpriced",
  unknown: "Unrated",
};

export function PriceActivityPanel({ state }: { state: PriceState }) {
  const { status, frames, action, analysis, stats, userListing, currency } =
    state;
  const analyzing = status === "analyzing";
  const done = status === "done";
  const verdict = (analysis?.verdict as string) || "";

  // The scraper steps come from the frames; the Gemini phase + result are
  // synthesized tail nodes so the timeline reads as one continuous run.
  const steps = frames.map((f) => ({ key: `f${f.step}`, label: f.action }));

  return (
    <div className="pact">
      <div className="pact-head">
        <span className="pact-title">Price agent</span>
        <span className="pact-sub">scrape · vision · evaluate</span>
      </div>

      <div className="pact-timeline">
        <AnimatePresence initial={false}>
          {steps.map((s, i) => {
            const isLast = i === steps.length - 1;
            const running = isLast && status === "streaming";
            return (
              <motion.div
                key={s.key}
                className="pact-step"
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3, ease: EASE }}
              >
                <span
                  className={`pact-pip${running ? " pact-pip--run" : " pact-pip--ok"}`}
                  aria-hidden="true"
                />
                <span className="pact-step-label">{s.label}</span>
              </motion.div>
            );
          })}

          {(analyzing || done) && (
            <motion.div
              key="gemini"
              className="pact-step"
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, ease: EASE }}
            >
              <span
                className={`pact-pip${analyzing ? " pact-pip--run" : " pact-pip--ok"}`}
                aria-hidden="true"
              />
              <span className="pact-step-label">
                Gemini · matching your seat &amp; grading the price
              </span>
            </motion.div>
          )}
        </AnimatePresence>

        {status === "streaming" && !steps.length && (
          <div className="pact-step">
            <span className="pact-pip pact-pip--run" aria-hidden="true" />
            <span className="pact-step-label">{action || "Opening market…"}</span>
          </div>
        )}
      </div>

      {/* Result block: the buyer's ticket vs market + verdict. */}
      {done && (
        <motion.div
          className="pact-result"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: EASE }}
        >
          {verdict && (
            <span className={`pact-verdict pact-verdict--${verdict}`}>
              {VERDICT_LABEL[verdict] ?? verdict}
            </span>
          )}
          <div className="pact-figures">
            {userListing?.price_per_ticket != null && (
              <div className="pact-fig">
                <span className="pact-fig-label">Your ticket</span>
                <strong>{fmtMoney(userListing.price_per_ticket, currency)}</strong>
              </div>
            )}
            {stats?.median != null && (
              <div className="pact-fig">
                <span className="pact-fig-label">Market median</span>
                <strong>{fmtMoney(stats.median, currency)}</strong>
              </div>
            )}
            {stats?.percentile != null && (
              <div className="pact-fig">
                <span className="pact-fig-label">Percentile</span>
                <strong>P{stats.percentile}</strong>
              </div>
            )}
          </div>
          {analysis?.headline && (
            <p className="pact-headline">{analysis.headline}</p>
          )}
        </motion.div>
      )}
    </div>
  );
}

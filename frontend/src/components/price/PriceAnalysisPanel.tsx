import { motion } from "framer-motion";
import type { PriceState, PriceVerdict } from "./usePriceStream";
import "./PriceAnalysisPanel.css";

const EASE = [0.22, 1, 0.36, 1] as const;

function fmtUsd(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

const VERDICT_META: Record<
  PriceVerdict,
  { label: string; emoji: string; tone: string }
> = {
  good_deal: { label: "Good deal", emoji: "🟢", tone: "good" },
  fair: { label: "Fair price", emoji: "🟡", tone: "fair" },
  slightly_high: { label: "A bit high", emoji: "🟠", tone: "warn" },
  overpriced: { label: "Overpriced", emoji: "🔴", tone: "bad" },
  unknown: { label: "Unrated", emoji: "⚪", tone: "unknown" },
};

export function PriceAnalysisPanel({ state }: { state: PriceState }) {
  const { status, analysis, stats, userListing, recommendations } = state;

  if (status === "analyzing") {
    return (
      <div className="pap clay">
        <div className="pap-skeleton">
          <span className="pap-spinner" aria-hidden="true" />
          Evaluating this price against the live market…
        </div>
      </div>
    );
  }

  if (status !== "done" || !analysis) return null;

  const verdict = (analysis.verdict as PriceVerdict) || "unknown";
  const meta = VERDICT_META[verdict] ?? VERDICT_META.unknown;

  return (
    <motion.div
      className={`pap clay pap--${meta.tone}`}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: EASE }}
    >
      <div className="pap-head">
        <span className="pap-badge" aria-hidden="true">
          {meta.emoji}
        </span>
        <div>
          <span className="pap-verdict">{meta.label}</span>
          {analysis.headline && (
            <p className="pap-headline">{analysis.headline}</p>
          )}
        </div>
        {stats?.percentile != null && (
          <span className="pap-percentile" title="Where this price sits in the market">
            P{stats.percentile}
          </span>
        )}
      </div>

      {analysis.assessment && (
        <p className="pap-assessment">{analysis.assessment}</p>
      )}

      <div className="pap-figures">
        {userListing?.price_per_ticket != null && (
          <div className="pap-fig neu-inset">
            <span className="pap-fig-label">Your ticket</span>
            <strong>{fmtUsd(userListing.price_per_ticket)}</strong>
            {userListing.section && (
              <span className="pap-fig-sub">Sec {userListing.section}</span>
            )}
          </div>
        )}
        {stats?.median != null && (
          <div className="pap-fig neu-inset">
            <span className="pap-fig-label">Market median</span>
            <strong>{fmtUsd(stats.median)}</strong>
            {stats.count != null && (
              <span className="pap-fig-sub">{stats.count} listings</span>
            )}
          </div>
        )}
        {stats?.fair_price_range && (
          <div className="pap-fig neu-inset">
            <span className="pap-fig-label">Fair range</span>
            <strong>
              {fmtUsd(stats.fair_price_range.low)}–
              {fmtUsd(stats.fair_price_range.high)}
            </strong>
          </div>
        )}
      </div>

      {analysis.savings_hint && (
        <p className="pap-hint">💡 {analysis.savings_hint}</p>
      )}

      {analysis.tips && analysis.tips.length > 0 && (
        <ul className="pap-tips">
          {analysis.tips.map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </ul>
      )}

      {recommendations.length > 0 && (
        <div className="pap-recs">
          <span className="pap-recs-title">Better-value seats</span>
          <ul>
            {recommendations.map((r, i) => (
              <li key={r.listing_id ?? i} className="pap-rec neu-inset">
                <strong>{fmtUsd(r.price)}</strong>
                <span className="pap-rec-seat">
                  Sec {r.section ?? "—"}
                  {r.row != null ? ` · Row ${r.row}` : ""}
                </span>
                {Array.isArray(r.badges) && r.badges.length > 0 && (
                  <span className="pap-rec-badge">{r.badges[0]}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </motion.div>
  );
}

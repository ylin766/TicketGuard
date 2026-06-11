import { motion } from "framer-motion";
import type { SeatScore, SeatDimensionKey } from "./usePriceStream";
import "./SeatScoreCard.css";

const EASE = [0.22, 1, 0.36, 1] as const;

const API_ORIGIN = "http://localhost:8001";

/** Human labels for each rubric dimension, in display order. */
const DIMENSION_LABELS: Record<SeatDimensionKey, string> = {
  view_clarity: "View clarity",
  proximity: "Proximity",
  value: "Value",
  obstruction: "Unobstructed",
  atmosphere: "Atmosphere",
};

const DIMENSION_ORDER: SeatDimensionKey[] = [
  "view_clarity",
  "proximity",
  "value",
  "obstruction",
  "atmosphere",
];

const RING_META: Record<
  SeatScore["ring"],
  { label: string; tone: string }
> = {
  excellent: { label: "Excellent", tone: "excellent" },
  great: { label: "Great", tone: "great" },
  good: { label: "Good", tone: "good" },
  fair: { label: "Fair", tone: "fair" },
  poor: { label: "Poor", tone: "poor" },
};

/** Resolve a backend-relative photo URL (/seat-photos/…) to an absolute one. */
function resolvePhoto(url: string): string {
  return url.startsWith("http") ? url : `${API_ORIGIN}${url}`;
}

export interface SeatScoreCardProps {
  section: string;
  price?: number | null;
  currency?: string;
  photoUrls?: string[];
  score: SeatScore;
  /** Highlight this card as the buyer's own listing (from the audited URL). */
  isYours?: boolean;
}

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

/**
 * Renders the seat agent's structured grade for one section: a representative
 * seat-view photo, the weighted overall + ring badge, and a bar per rubric
 * dimension (hover shows the model's note).
 */
export function SeatScoreCard({
  section,
  price,
  currency = "USD",
  photoUrls,
  score,
  isYours = false,
}: SeatScoreCardProps) {
  const ring = RING_META[score.ring] ?? RING_META.good;
  const hero = photoUrls && photoUrls.length > 0 ? photoUrls[0] : null;

  return (
    <motion.div
      className={`ssc clay ssc--${ring.tone}${isYours ? " ssc--yours" : ""}`}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: EASE }}
    >
      {isYours && <span className="ssc-yours-tag">Your seat</span>}
      <div className="ssc-head">
        {hero && (
          <div className="ssc-photo neu-inset">
            <img src={resolvePhoto(hero)} alt={`Section ${section} view`} loading="lazy" />
          </div>
        )}
        <div className="ssc-head-meta">
          <span className="ssc-section">Section {section}</span>
          {price != null && (
            <span className="ssc-price">{fmtMoney(price, currency)}</span>
          )}
          <div className="ssc-overall">
            <span className="ssc-overall-num">{score.overall}</span>
            <span className={`ssc-ring ssc-ring--${ring.tone}`}>{ring.label}</span>
          </div>
        </div>
      </div>

      <div className="ssc-dims">
        {DIMENSION_ORDER.map((key) => {
          const dim = score.dimensions[key];
          if (!dim) return null;
          return (
            <div className="ssc-dim" key={key} title={dim.note}>
              <span className="ssc-dim-label">{DIMENSION_LABELS[key]}</span>
              <div className="ssc-dim-track neu-inset">
                <motion.div
                  className="ssc-dim-fill"
                  initial={{ width: 0 }}
                  animate={{ width: `${dim.score}%` }}
                  transition={{ duration: 0.6, ease: EASE }}
                />
              </div>
              <span className="ssc-dim-score">{dim.score}</span>
            </div>
          );
        })}
      </div>

      {score.summary && <p className="ssc-summary">{score.summary}</p>}

      <span className={`ssc-confidence ssc-confidence--${score.confidence}`}>
        {score.confidence} confidence
      </span>
    </motion.div>
  );
}

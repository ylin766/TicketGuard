import { motion } from "framer-motion";
import type { PriceState } from "./usePriceStream";
import "./SeatOverview.css";

const EASE = [0.22, 1, 0.36, 1] as const;

/**
 * Stadium-wide seat coverage summary for the audited match, shown near the top
 * of the report. Aggregates the price listings' seat-photo match status so the
 * buyer sees, at a glance, how much of the venue we have real seat views for.
 */
export function SeatOverview({
  state,
  venue,
}: {
  state: PriceState;
  venue: string;
}) {
  if (state.status !== "done" || state.listings.length === 0) return null;

  const listings = state.listings;
  const withPhotos = listings.filter(
    (l) => (l.photo_count ?? 0) > 0
  );
  // Unique sections that have at least one seat-view photo.
  const coveredSections = new Set(
    withPhotos.map((l) => String(l.section ?? "")).filter(Boolean)
  );
  const graded = listings.filter((l) => l.seat_score != null);

  if (coveredSections.size === 0) return null;

  const totalSections = new Set(
    listings.map((l) => String(l.section ?? "")).filter(Boolean)
  ).size;

  return (
    <motion.section
      className="sov clay"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: EASE }}
    >
      <div className="sov-head">
        <span className="eyebrow">Seat overview</span>
        <h3 className="sov-title">{venue}</h3>
      </div>

      <div className="sov-stats">
        <div className="sov-stat neu-inset">
          <strong>{coveredSections.size}</strong>
          <span>sections with real views</span>
        </div>
        <div className="sov-stat neu-inset">
          <strong>{withPhotos.length}</strong>
          <span>listings with photos</span>
        </div>
        <div className="sov-stat neu-inset">
          <strong>{graded.length}</strong>
          <span>graded by seat agent</span>
        </div>
        <div className="sov-stat neu-inset">
          <strong>{totalSections}</strong>
          <span>sections on sale</span>
        </div>
      </div>
    </motion.section>
  );
}

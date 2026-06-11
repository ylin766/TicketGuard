import { motion } from "framer-motion";
import type { PriceState } from "./usePriceStream";
import { SeatScoreCard } from "./SeatScoreCard";
import "./SeatScorePanel.css";

const EASE = [0.22, 1, 0.36, 1] as const;

/**
 * Full-width panel of the seat agent's graded sections. Sits below the price
 * analysis in the report. Renders nothing until the price stream is done and at
 * least one listing was graded.
 */
export function SeatScorePanel({
  state,
  yourSection: yourSectionRaw,
}: {
  state: PriceState;
  /** Buyer's section from the report hero (preferred over userListing). */
  yourSection?: string | null;
}) {
  if (state.status !== "done") return null;

  // The buyer's own section: prefer the explicit prop (report hero, which has a
  // fallback), else the vision-extracted userListing.
  const yourSection =
    normSection(yourSectionRaw) ?? normSection(state.userListing?.section);

  const isYours = (l: PriceState["listings"][number]) =>
    yourSection != null && normSection(String(l.section ?? "")) === yourSection;

  const gradedSeats = state.listings
    .filter((l) => l.seat_score != null)
    .sort((a, b) => {
      // The buyer's own seat always leads, then best overall first.
      const ay = isYours(a) ? 1 : 0;
      const by = isYours(b) ? 1 : 0;
      if (ay !== by) return by - ay;
      return (b.seat_score!.overall ?? 0) - (a.seat_score!.overall ?? 0);
    });

  if (gradedSeats.length === 0) return null;

  const yoursGraded = gradedSeats.some(isYours);

  return (
    <motion.section
      className="ssp"
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: EASE }}
    >
      <div className="ssp-head clay">
        <span className="eyebrow">Seat agent</span>
        <h3 className="ssp-title">Seat views, graded</h3>
        <p className="ssp-sub">
          Real fan photos scored across five sightline dimensions.
          {yoursGraded
            ? " Your section is highlighted first."
            : yourSection != null
              ? ` We don't have a seat-view photo for your section (${yourSection}); comparable seats are shown below.`
              : ""}
        </p>
      </div>

      <div className="ssp-grid">
        {gradedSeats.map((l, i) => (
          <SeatScoreCard
            key={l.listing_id ?? `${l.section}-${i}`}
            section={String(l.section ?? "—")}
            price={typeof l.price === "number" ? l.price : null}
            currency={state.currency}
            photoUrls={l.photo_urls}
            score={l.seat_score!}
            isYours={isYours(l)}
          />
        ))}
      </div>
    </motion.section>
  );
}

/** Normalize a section id for comparison: lowercase, strip a letter suffix. */
function normSection(s: string | null | undefined): string | null {
  if (!s) return null;
  const m = String(s).trim().toLowerCase().match(/([a-z]{0,3})(\d{1,4})/);
  return m ? m[2] : String(s).trim().toLowerCase() || null;
}

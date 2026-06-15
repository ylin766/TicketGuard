import { useEffect, useRef, useState } from "react";

const PRICE_ENDPOINT = `${import.meta.env.VITE_API_URL || "http://localhost:8001"}/api/price/stream`;

export interface PriceFrame {
  step: number;
  action: string;
  /** data:image/png;base64,… */
  image: string;
  ts: number;
}

export interface PriceListing {
  price?: number | null;
  section?: string | null;
  row?: string | number | null;
  listing_id?: string | null;
  badges?: string[];
  /** Seat-photo match status (set by backend seats.match_seats). */
  match_status?:
    | "matched"
    | "matched_base"
    | "no_photo"
    | "category"
    | "supporters"
    | "unmatchable";
  /** Number of seat-view photos found for this section. */
  photo_count?: number;
  /** Public URLs for this section's seat-view photos (served at /seat-photos). */
  photo_urls?: string[];
  /** Seat-agent grade, present only for the top-N graded listings (else null). */
  seat_score?: SeatScore | null;
  [key: string]: unknown;
}

/** One graded dimension from the seat agent (0–100 + a short reason). */
export interface SeatDimension {
  score: number;
  note: string;
}

/** Keys of the seat-agent rubric (mirrors backend DIMENSION_WEIGHTS). */
export type SeatDimensionKey =
  | "view_clarity"
  | "proximity"
  | "value"
  | "obstruction"
  | "atmosphere";

/** The seat agent's structured grade for one section. */
export interface SeatScore {
  /** Weighted overall, 0–100. */
  overall: number;
  ring: "excellent" | "great" | "good" | "fair" | "poor";
  dimensions: Record<SeatDimensionKey, SeatDimension>;
  /** One-sentence buyer-facing takeaway. */
  summary: string;
  confidence: "high" | "medium" | "low";
}

/** One step in the seat agent's live trace (mirrors the price step timeline). */
export interface SeatStep {
  action: string;
  /** Public seat-photo URL for this step, if any (relative /seat-photos/…). */
  image?: string | null;
  ts: number;
}

/** The buyer's own ticket, extracted from the page by Gemini vision. */
export interface UserListing {
  event_name?: string | null;
  venue?: string | null;
  date?: string | null;
  section?: string | null;
  row?: string | null;
  seat?: string | null;
  quantity?: number | null;
  price_per_ticket?: number | null;
  total_price?: number | null;
  currency?: string | null;
  seller_notes?: string | null;
  confidence?: "high" | "medium" | "low" | string | null;
}

export interface PriceStats {
  count?: number;
  median?: number | null;
  min?: number | null;
  max?: number | null;
  percentile?: number | null;
  same_section_median?: number | null;
  same_section_count?: number;
  fair_price_range?: { low: number; high: number } | null;
  currency?: string;
}

export type PriceVerdict =
  | "good_deal"
  | "fair"
  | "slightly_high"
  | "overpriced"
  | "unknown";

export interface PriceAnalysis {
  verdict?: PriceVerdict | string;
  headline?: string;
  assessment?: string;
  savings_hint?: string | null;
  tips?: string[];
}

export type PriceStatus = "idle" | "streaming" | "analyzing" | "done" | "error";

export interface PriceState {
  status: PriceStatus;
  source: string | null;
  /** All screenshot frames received, in order. */
  frames: PriceFrame[];
  /** The most recent frame (what the viewport shows). */
  latestFrame: PriceFrame | null;
  /** Current action label (from the latest frame). */
  action: string | null;
  listings: PriceListing[];
  median: number | null;
  count: number;
  /** ISO currency code detected from the page (geo-localized). */
  currency: string;
  /** Buyer's own ticket (vision-extracted), {} until 'done'. */
  userListing: UserListing | null;
  /** The same seat located on our reference market (cross-site), {} if none. */
  sameSeat: PriceListing | null;
  stats: PriceStats | null;
  analysis: PriceAnalysis | null;
  recommendations: PriceListing[];
  /** Live seat-agent trace steps (photo match + per-section grading). */
  seatSteps: SeatStep[];
  /** Most recent seat photo shown in the seat viewport. */
  seatImage: string | null;
  error: string | null;
}

const INITIAL: PriceState = {
  status: "idle",
  source: null,
  frames: [],
  latestFrame: null,
  action: null,
  listings: [],
  median: null,
  count: 0,
  currency: "USD",
  userListing: null,
  sameSeat: null,
  stats: null,
  analysis: null,
  recommendations: [],
  seatSteps: [],
  seatImage: null,
  error: null,
};

type PriceSseFrame =
  | { type: "start"; url: string; source: string }
  | { type: "frame"; step: number; action: string; image: string; ts: number }
  | { type: "analyzing"; ts: number }
  | { type: "seat"; action: string; image?: string | null; ts: number }
  | {
      type: "done";
      median: number | null;
      count: number;
      listings: PriceListing[];
      metadata?: Record<string, unknown>;
      user_listing?: UserListing;
      same_seat?: PriceListing;
      stats?: PriceStats;
      analysis?: PriceAnalysis;
      recommendations?: PriceListing[];
    }
  | { type: "error"; message: string };

/**
 * Consume the live price-collection SSE stream for a URL. Pass `enabled=false`
 * to hold off until the price step should begin. Returns the accumulated state,
 * updated live as screenshot frames + the final median arrive.
 */
export function usePriceStream(
  url: string,
  qty: number,
  enabled: boolean
): PriceState {
  const [state, setState] = useState<PriceState>(INITIAL);
  const doneRef = useRef(false);

  useEffect(() => {
    if (!enabled || !url) return;
    setState({ ...INITIAL, status: "streaming" });
    doneRef.current = false;
    const controller = new AbortController();

    const apply = (frame: PriceSseFrame) => {
      setState((prev) => {
        switch (frame.type) {
          case "start":
            return { ...prev, status: "streaming", source: frame.source };
          case "frame": {
            const f: PriceFrame = {
              step: frame.step,
              action: frame.action,
              image: frame.image,
              ts: frame.ts,
            };
            return {
              ...prev,
              frames: [...prev.frames, f],
              latestFrame: f,
              action: frame.action,
            };
          }
          case "analyzing":
            return { ...prev, status: "analyzing" };
          case "seat":
            return {
              ...prev,
              seatSteps: [
                ...prev.seatSteps,
                { action: frame.action, image: frame.image, ts: frame.ts },
              ],
              seatImage: frame.image ?? prev.seatImage,
            };
          case "done":
            return {
              ...prev,
              status: "done",
              median: frame.median,
              count: frame.count,
              listings: frame.listings ?? [],
              currency: frame.stats?.currency ?? prev.currency,
              userListing: frame.user_listing ?? null,
              sameSeat: frame.same_seat ?? null,
              stats: frame.stats ?? null,
              analysis: frame.analysis ?? null,
              recommendations: frame.recommendations ?? [],
            };
          case "error":
            return { ...prev, status: "error", error: frame.message };
          default:
            return prev;
        }
      });
    };

    const streamUrl = `${PRICE_ENDPOINT}?url=${encodeURIComponent(url)}&qty=${qty}`;
    fetch(streamUrl, { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`Server error ${res.status}`);
        if (!res.body) throw new Error("No response body");
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const json = line.slice(6).trim();
            if (!json) continue;
            try {
              apply(JSON.parse(json) as PriceSseFrame);
            } catch {
              /* ignore malformed frame */
            }
          }
        }
        doneRef.current = true;
      })
      .catch((err: Error) => {
        if (err.name === "AbortError") return;
        setState((prev) => ({ ...prev, status: "error", error: err.message }));
      });

    return () => controller.abort();
  }, [url, qty, enabled]);

  return state;
}

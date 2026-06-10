import { useEffect, useRef, useState } from "react";

const PRICE_ENDPOINT = "http://localhost:8001/api/price/stream";

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
  [key: string]: unknown;
}

export type PriceStatus = "idle" | "streaming" | "done" | "error";

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
  error: null,
};

type PriceSseFrame =
  | { type: "start"; url: string; source: string }
  | { type: "frame"; step: number; action: string; image: string; ts: number }
  | {
      type: "done";
      median: number | null;
      count: number;
      listings: PriceListing[];
      metadata?: Record<string, unknown>;
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
          case "done":
            return {
              ...prev,
              status: "done",
              median: frame.median,
              count: frame.count,
              listings: frame.listings ?? [],
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

import { useEffect, useRef, useState } from "react";

const BROWSER_ENDPOINT = "http://localhost:8001/api/security/browser-stream";

export interface BrowserFrame {
  step: number;
  action: string;
  /** data:image/png;base64,… */
  image: string;
  ts: number;
}

/** Brand / domain consistency the probe verified. */
export interface BrandCheck {
  claimed_platform: string | null;
  claimed_event: string | null;
  domain: string | null;
  /** true = brand matches its domain, false = mismatch, null = no brand claimed. */
  matches: boolean | null;
  trusted: boolean | null;
  mismatch_reason: string | null;
  off_platform_payment: boolean | null;
}

/** One sensitive surface the probe reached + what it demands. */
export interface SensitiveSurface {
  page_state: string;
  reached: boolean;
  action_types: string[];
  requested_inputs: string[];
}

export type BrowserCheckStatus = "idle" | "streaming" | "done" | "error";

export interface BrowserCheckState {
  status: BrowserCheckStatus;
  frames: BrowserFrame[];
  latestFrame: BrowserFrame | null;
  action: string | null;
  verdict: string | null;
  riskLevel: string | null;
  riskScore: number | null;
  summary: string | null;
  brand: BrandCheck | null;
  sensitiveSurfaces: SensitiveSurface[];
  error: string | null;
}

const INITIAL: BrowserCheckState = {
  status: "idle",
  frames: [],
  latestFrame: null,
  action: null,
  verdict: null,
  riskLevel: null,
  riskScore: null,
  summary: null,
  brand: null,
  sensitiveSurfaces: [],
  error: null,
};

type BrowserSseFrame =
  | { type: "start"; url: string; agent: string }
  | { type: "frame"; step: number; action: string; image: string; ts: number }
  | {
      type: "done";
      verdict: string | null;
      risk_level: string | null;
      risk_score: number | null;
      summary: string | null;
      brand?: BrandCheck | null;
      sensitive_surfaces?: SensitiveSurface[];
    }
  | { type: "error"; message: string };

/**
 * Consume the Layer-2 browser-check SSE stream for a URL, exposing the agent's
 * live screenshots + final verdict. Pass ``enabled=false`` to hold off until the
 * security step (grey-zone escalation) should begin.
 */
export function useBrowserCheckStream(
  url: string,
  enabled: boolean
): BrowserCheckState {
  const [state, setState] = useState<BrowserCheckState>(INITIAL);
  const doneRef = useRef(false);

  useEffect(() => {
    if (!enabled || !url) return;
    setState({ ...INITIAL, status: "streaming" });
    doneRef.current = false;
    const controller = new AbortController();

    const apply = (frame: BrowserSseFrame) => {
      setState((prev) => {
        switch (frame.type) {
          case "start":
            return { ...prev, status: "streaming" };
          case "frame": {
            const f: BrowserFrame = {
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
              verdict: frame.verdict,
              riskLevel: frame.risk_level,
              riskScore: frame.risk_score,
              summary: frame.summary,
              brand: frame.brand ?? null,
              sensitiveSurfaces: frame.sensitive_surfaces ?? [],
            };
          case "error":
            return { ...prev, status: "error", error: frame.message };
          default:
            return prev;
        }
      });
    };

    const streamUrl = `${BROWSER_ENDPOINT}?url=${encodeURIComponent(url)}`;
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
              apply(JSON.parse(json) as BrowserSseFrame);
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
  }, [url, enabled]);

  return state;
}

import { useEffect, useRef, useState } from "react";
import type {
  OsintFrame,
  OsintStep,
  OsintTokenTotals,
  OsintStatus,
} from "./types";

const OSINT_ENDPOINT = "http://localhost:8001/api/osint/stream";

export interface OsintState {
  status: OsintStatus;
  /** The agent's interim reasoning lines, in order. */
  thoughts: string[];
  /** Tool calls (merged with their results) in order. */
  steps: OsintStep[];
  tokens: OsintTokenTotals;
  /** Final parsed report (score + tier + text), or null until done. */
  report: { score: number | null; tier: string | null; text: string } | null;
  /** Aggregate stats from the done frame. */
  stats: {
    steps: number;
    toolCalls: number;
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
    durationMs: number;
  } | null;
  phoenixUrl: string | null;
  error: string | null;
}

const INITIAL: OsintState = {
  status: "idle",
  thoughts: [],
  steps: [],
  tokens: { prompt: 0, completion: 0, total: 0 },
  report: null,
  stats: null,
  phoenixUrl: null,
  error: null,
};

/**
 * Consume the OSINT agent's SSE trace for a URL. Pass `enabled=false` to hold
 * off until the investigation should begin (e.g. after the threat scan).
 *
 * Returns the accumulated trace state, updated live as frames arrive. The
 * `onDone` callback fires once the stream settles (done or error).
 */
export function useOsintStream(
  url: string,
  enabled: boolean,
  onDone?: () => void
): OsintState {
  const [state, setState] = useState<OsintState>(INITIAL);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;
  const doneFiredRef = useRef(false);

  useEffect(() => {
    if (!enabled || !url) return;

    setState({ ...INITIAL, status: "streaming" });
    doneFiredRef.current = false;
    const controller = new AbortController();

    const fireDone = () => {
      if (doneFiredRef.current) return;
      doneFiredRef.current = true;
      onDoneRef.current?.();
    };

    const apply = (frame: OsintFrame) => {
      setState((prev) => {
        switch (frame.type) {
          case "start":
            return { ...prev, status: "streaming" };
          case "thinking":
            return { ...prev, thoughts: [...prev.thoughts, frame.text] };
          case "tool_call":
            return {
              ...prev,
              steps: [
                ...prev.steps,
                {
                  id: frame.id,
                  tool: frame.tool,
                  label: frame.label,
                  source: frame.source,
                  args: frame.args,
                  status: "running",
                  durationMs: null,
                  chars: null,
                  preview: null,
                },
              ],
            };
          case "tool_result":
            return {
              ...prev,
              steps: prev.steps.map((s) =>
                s.id === frame.id || (s.tool === frame.tool && s.status === "running")
                  ? {
                      ...s,
                      status: frame.ok ? "ok" : "fail",
                      durationMs: frame.duration_ms,
                      chars: frame.chars,
                      preview: frame.preview,
                    }
                  : s
              ),
            };
          case "tokens":
            return {
              ...prev,
              tokens: {
                prompt: prev.tokens.prompt + frame.prompt,
                completion: prev.tokens.completion + frame.completion,
                total: prev.tokens.total + frame.total,
              },
            };
          case "report":
            return {
              ...prev,
              report: { score: frame.score, tier: frame.tier, text: frame.text },
            };
          case "done":
            return {
              ...prev,
              status: "done",
              phoenixUrl: frame.phoenix_url,
              stats: {
                steps: frame.stats.steps,
                toolCalls: frame.stats.tool_calls,
                promptTokens: frame.stats.prompt_tokens,
                completionTokens: frame.stats.completion_tokens,
                totalTokens: frame.stats.total_tokens,
                durationMs: frame.stats.duration_ms,
              },
            };
          case "error":
            return { ...prev, status: "error", error: frame.message };
          default:
            return prev;
        }
      });
    };

    const streamUrl = `${OSINT_ENDPOINT}?url=${encodeURIComponent(url)}`;
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
              apply(JSON.parse(json) as OsintFrame);
            } catch {
              /* ignore malformed frame */
            }
          }
        }
        fireDone();
      })
      .catch((err: Error) => {
        if (err.name === "AbortError") return;
        setState((prev) => ({ ...prev, status: "error", error: err.message }));
        fireDone();
      });

    return () => controller.abort();
  }, [url, enabled]);

  return state;
}

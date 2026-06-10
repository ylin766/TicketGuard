import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useFlow, FLOW_ORDER } from "./useFlow";

// usePrefersReducedMotion reads window.matchMedia at render time.
function mockReducedMotion(reduced: boolean) {
  vi.stubGlobal(
    "matchMedia",
    (query: string) =>
      ({
        matches: reduced,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList,
  );
  // jsdom attaches matchMedia to window too.
  window.matchMedia = globalThis.matchMedia;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useFlow state machine", () => {
  it("starts on the input phase", () => {
    mockReducedMotion(false);
    const { result } = renderHook(() => useFlow());
    expect(result.current.phase).toBe("input");
    expect(result.current.started).toBe(false);
  });

  it("start() moves to dispatch and stores the url (motion on)", () => {
    mockReducedMotion(false);
    const { result } = renderHook(() => useFlow());
    act(() => result.current.start("stubhub.com/listing/1"));
    expect(result.current.phase).toBe("dispatch");
    expect(result.current.url).toBe("stubhub.com/listing/1");
    expect(result.current.started).toBe(true);
  });

  it("advance() walks through the phases in order", () => {
    mockReducedMotion(false);
    const { result } = renderHook(() => useFlow());
    act(() => result.current.start("example.com"));

    for (let i = FLOW_ORDER.indexOf("dispatch"); i < FLOW_ORDER.length - 1; i++) {
      const from = FLOW_ORDER[i];
      const next = FLOW_ORDER[i + 1];
      expect(result.current.phase).toBe(from);
      act(() => result.current.advance(from));
      expect(result.current.phase).toBe(next);
    }
    expect(result.current.phase).toBe("report");
  });

  it("advance() ignores a stale phase (no skipping)", () => {
    mockReducedMotion(false);
    const { result } = renderHook(() => useFlow());
    act(() => result.current.start("example.com")); // dispatch
    // Calling advance for the wrong phase must not move the machine.
    act(() => result.current.advance("pipeline"));
    expect(result.current.phase).toBe("dispatch");
  });

  it("advance() does not go past report", () => {
    mockReducedMotion(false);
    const { result } = renderHook(() => useFlow());
    act(() => result.current.start("example.com"));
    for (const from of ["dispatch", "split", "pipeline"] as const) {
      act(() => result.current.advance(from));
    }
    expect(result.current.phase).toBe("report");
    act(() => result.current.advance("report"));
    expect(result.current.phase).toBe("report");
  });

  it("reduced motion skips the decorative beats but keeps the pipeline (a11y)", () => {
    mockReducedMotion(true);
    const { result } = renderHook(() => useFlow());
    act(() => result.current.start("example.com"));
    // Goes straight to the pipeline (not report): the audit data is gathered
    // there and the report is assembled from it.
    expect(result.current.phase).toBe("pipeline");
  });

  it("reset() returns to input and clears state", () => {
    mockReducedMotion(false);
    const { result } = renderHook(() => useFlow());
    act(() => result.current.start("example.com"));
    act(() => result.current.reset());
    expect(result.current.phase).toBe("input");
    expect(result.current.url).toBeNull();
    expect(result.current.started).toBe(false);
  });
});

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThreatIntelPanel } from "./ThreatIntelPanel";
import { CLEAN_SOURCES, FLAGGED_SOURCES } from "./threatintel/fixtures";
import type { ThreatSource } from "../types";

const TEST_URL = "https://example-ticket-site.com/listing/123";

// ---------------------------------------------------------------------------
// SSE mock helpers — the component reads res.body.getReader() and parses
// `data: {...}\n\n` lines, so we build a ReadableStream of those events.
// ---------------------------------------------------------------------------

function sseStream(sources: ThreatSource[], flagged: boolean, status = "ok") {
  const encoder = new TextEncoder();
  const frames: string[] = [
    ...sources.map(
      (s) => `data: ${JSON.stringify({ type: "source", data: s })}\n\n`
    ),
    `data: ${JSON.stringify({ type: "done", status, flagged })}\n\n`,
  ];
  return new ReadableStream({
    start(controller) {
      for (const f of frames) controller.enqueue(encoder.encode(f));
      controller.close();
    },
  });
}

function mockSse(sources: ThreatSource[], flagged: boolean, status = "ok") {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(sseStream(sources, flagged, status), {
      headers: { "Content-Type": "text/event-stream" },
      status: 200,
    })
  );
}

/** A stream that emits the given sources then stays OPEN (no done event), so
 *  the panel remains in the streaming/pending state for assertions. */
function mockPartialSse(sources: ThreatSource[]) {
  const encoder = new TextEncoder();
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      new ReadableStream({
        start(controller) {
          for (const s of sources) {
            controller.enqueue(
              encoder.encode(`data: ${JSON.stringify({ type: "source", data: s })}\n\n`)
            );
          }
          // Intentionally never close → stays "streaming".
        },
      }),
      { headers: { "Content-Type": "text/event-stream" }, status: 200 }
    )
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Panel-level: verdict summary, grouping, states
// ---------------------------------------------------------------------------

describe("ThreatIntelPanel", () => {
  it("shows a loading state while the stream is open", () => {
    vi.spyOn(globalThis, "fetch").mockReturnValue(new Promise(() => {}));
    render(<ThreatIntelPanel url={TEST_URL} />);
    // The streaming dots carry the exact "Loading" label (skeletons use
    // "<name> loading", so match exactly to target the dots).
    expect(screen.getByLabelText("Loading")).toBeInTheDocument();
  });

  it("shows CLEAN badge and groups sources when not flagged", async () => {
    mockSse(CLEAN_SOURCES, false);
    render(<ThreatIntelPanel url={TEST_URL} />);

    await waitFor(() => expect(screen.getByText("CLEAN")).toBeInTheDocument());

    // Both groups render (default expanded).
    expect(screen.getByText("Threat scan")).toBeInTheDocument();
    expect(screen.getByText("Domain intelligence")).toBeInTheDocument();

    // A finding and a context source each render their panel.
    expect(screen.getByText("VirusTotal")).toBeInTheDocument();
    expect(screen.getByText("RDAP")).toBeInTheDocument();
  });

  it("shows FLAGGED badge and an alert count in the summary", async () => {
    mockSse(FLAGGED_SOURCES, true);
    render(<ThreatIntelPanel url={TEST_URL} />);

    await waitFor(() => expect(screen.getByText("FLAGGED")).toBeInTheDocument());
    // Summary line mentions the flagged count (e.g. "… · 5 flagged · …").
    expect(screen.getByText(/\d+ flagged/i)).toBeInTheDocument();
  });

  it("collapses and expands the source groups on header click", async () => {
    const user = userEvent.setup();
    mockSse(CLEAN_SOURCES, false);
    render(<ThreatIntelPanel url={TEST_URL} />);

    await waitFor(() => expect(screen.getByText("VirusTotal")).toBeInTheDocument());

    const header = screen.getByRole("button", { name: /threat intelligence/i });
    await user.click(header); // collapse
    await waitFor(() =>
      expect(screen.queryByText("VirusTotal")).not.toBeInTheDocument()
    );

    await user.click(header); // expand again
    expect(screen.getByText("VirusTotal")).toBeInTheDocument();
  });

  it("shows an error message when the request fails", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("Network down"));
    render(<ThreatIntelPanel url={TEST_URL} />);
    await waitFor(() =>
      expect(
        screen.getByText(/Could not reach the threat-intel server/i)
      ).toBeInTheDocument()
    );
  });

  it("shows the unavailable message when no sources return", async () => {
    mockSse([], false, "unavailable");
    render(<ThreatIntelPanel url={TEST_URL} />);
    await waitFor(() =>
      expect(
        screen.getByText(/No threat-intel sources returned a result/i)
      ).toBeInTheDocument()
    );
  });
});

// ---------------------------------------------------------------------------
// Source-level: each panel renders its native fields correctly
// ---------------------------------------------------------------------------

describe("SourcePanel field rendering (via the full panel)", () => {
  it("renders the VirusTotal engine ratio", async () => {
    mockSse(CLEAN_SOURCES, false);
    render(<ThreatIntelPanel url={TEST_URL} />);
    await waitFor(() => screen.getByText("VirusTotal"));

    const vt = screen.getByText("VirusTotal").closest(".ti-spanel") as HTMLElement;
    expect(within(vt).getByText("engines")).toBeInTheDocument();
    // The ratio renders the engine total inside the .ti-ratio-sep span.
    expect(within(vt).getByText(/\/ 91/)).toBeInTheDocument();
  });

  it("renders RDAP domain age and status chips", async () => {
    mockSse(CLEAN_SOURCES, false);
    render(<ThreatIntelPanel url={TEST_URL} />);
    await waitFor(() => screen.getByText("RDAP"));

    const rdap = screen.getByText("RDAP").closest(".ti-spanel") as HTMLElement;
    expect(within(rdap).getByText("domain age")).toBeInTheDocument();
    // 1995 registration → many years old.
    expect(within(rdap).getByText(/yrs?/)).toBeInTheDocument();
  });

  it("renders the Tranco rank", async () => {
    mockSse(CLEAN_SOURCES, false);
    render(<ThreatIntelPanel url={TEST_URL} />);
    await waitFor(() => screen.getByText("Tranco"));

    const tranco = screen.getByText("Tranco").closest(".ti-spanel") as HTMLElement;
    expect(within(tranco).getByText("#180")).toBeInTheDocument();
  });

  it("renders SafeBrowsing threat-type chips when flagged", async () => {
    mockSse(FLAGGED_SOURCES, true);
    render(<ThreatIntelPanel url={TEST_URL} />);
    await waitFor(() => screen.getByText("SafeBrowsing"));

    const sb = screen.getByText("SafeBrowsing").closest(".ti-spanel") as HTMLElement;
    // Chips lowercase + space-separate the threat types.
    expect(within(sb).getByText("social engineering")).toBeInTheDocument();
    expect(within(sb).getByText("malware")).toBeInTheDocument();
  });

  it("renders the IPGeo country", async () => {
    mockSse(CLEAN_SOURCES, false);
    render(<ThreatIntelPanel url={TEST_URL} />);
    await waitFor(() => screen.getByText("IPGeo"));

    const geo = screen.getByText("IPGeo").closest(".ti-spanel") as HTMLElement;
    expect(within(geo).getByText("Canada")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Skeleton placeholders, themes, and stable layout while streaming
// ---------------------------------------------------------------------------

describe("ThreatIntelPanel streaming placeholders", () => {
  it("shows themed skeletons for sources that have not arrived yet", async () => {
    // Only VirusTotal has arrived; the rest stay pending.
    const vt = CLEAN_SOURCES.find((s) => s.name === "VirusTotal")!;
    mockPartialSse([vt]);
    render(<ThreatIntelPanel url={TEST_URL} />);

    // The arrived source renders as a real panel.
    await waitFor(() => screen.getByText("VirusTotal"));

    // A not-yet-arrived source renders a busy skeleton.
    const sucuri = await screen.findByLabelText("Sucuri loading");
    expect(sucuri).toHaveAttribute("aria-busy", "true");

    // Both groups exist and every manifest source has a slot (stable layout).
    expect(screen.getByText("Threat scan")).toBeInTheDocument();
    expect(screen.getByText("Domain intelligence")).toBeInTheDocument();
  });

  it("applies a category theme class to each source panel", async () => {
    mockSse(CLEAN_SOURCES, false);
    render(<ThreatIntelPanel url={TEST_URL} />);
    await waitFor(() => screen.getByText("VirusTotal"));

    const vt = screen.getByText("VirusTotal").closest(".ti-spanel") as HTMLElement;
    expect(vt.className).toContain("ti-theme--malware");

    const rdap = screen.getByText("RDAP").closest(".ti-spanel") as HTMLElement;
    expect(rdap.className).toContain("ti-theme--registry");

    const geo = screen.getByText("IPGeo").closest(".ti-spanel") as HTMLElement;
    expect(geo.className).toContain("ti-theme--network");
  });

  it("keeps an unreturned source as a timed-out panel once done", async () => {
    // crt.sh is omitted from the response (e.g. it errored / timed out server-side).
    const withoutCrt = CLEAN_SOURCES.filter((s) => s.name !== "crt.sh");
    mockSse(withoutCrt, false);
    render(<ThreatIntelPanel url={TEST_URL} />);

    await waitFor(() => expect(screen.getByText("CLEAN")).toBeInTheDocument());
    // crt.sh still has a slot, now marked as timed out (not silently dropped).
    const crt = screen.getByText("crt.sh").closest(".ti-spanel") as HTMLElement;
    expect(crt.className).toContain("ti-spanel--timeout");
    expect(within(crt).getByText(/timed out/i)).toBeInTheDocument();
  });
});

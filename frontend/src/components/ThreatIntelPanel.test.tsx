import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThreatIntelPanel } from "./ThreatIntelPanel";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TEST_URL = "https://example-ticket-site.com/listing/123";

/** Build a minimal ThreatIntelResult-shaped response body. */
function makeResult(overrides: object = {}) {
  return {
    status: "ok",
    flagged: false,
    findings: [],
    context: [],
    detail: "",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Setup: mock global fetch before each test
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ThreatIntelPanel", () => {
  it("shows loading spinner while fetch is in progress", () => {
    // Never resolving fetch → spinner stays visible
    vi.spyOn(globalThis, "fetch").mockReturnValue(new Promise(() => {}));

    render(<ThreatIntelPanel url={TEST_URL} />);

    expect(screen.getByText(/Running threat intelligence checks/i)).toBeInTheDocument();
  });

  it("shows error message when fetch fails", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("Network down"));

    render(<ThreatIntelPanel url={TEST_URL} />);

    await waitFor(() =>
      expect(
        screen.getByText(/Could not reach the threat-intel server/i)
      ).toBeInTheDocument()
    );
  });

  it("shows CLEAN badge when flagged=false", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(makeResult({ flagged: false })), {
        headers: { "Content-Type": "application/json" },
      })
    );

    render(<ThreatIntelPanel url={TEST_URL} />);

    await waitFor(() =>
      expect(screen.getByText("CLEAN")).toBeInTheDocument()
    );
  });

  it("shows FLAGGED badge when flagged=true", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify(makeResult({ flagged: true })),
        { headers: { "Content-Type": "application/json" } }
      )
    );

    render(<ThreatIntelPanel url={TEST_URL} />);

    await waitFor(() =>
      expect(screen.getByText("FLAGGED")).toBeInTheDocument()
    );
  });

  it("shows source rows after clicking expand", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify(
          makeResult({
            findings: [
              { name: "Sucuri", threat: false, detail: "No Sucuri blacklist or malware warning." },
            ],
            context: [
              { name: "Tranco", threat: null, detail: "example-ticket-site.com is not on the Tranco list." },
            ],
          })
        ),
        { headers: { "Content-Type": "application/json" } }
      )
    );

    render(<ThreatIntelPanel url={TEST_URL} />);

    // Wait for data to load
    await waitFor(() => screen.getByText("CLEAN"));

    // Rows not visible yet (collapsed)
    expect(screen.queryByText("Sucuri")).not.toBeInTheDocument();

    // Click to expand
    await user.click(screen.getByRole("button", { name: /threat intel sources/i }));

    expect(screen.getByText("Sucuri")).toBeInTheDocument();
    expect(screen.getByText("Tranco")).toBeInTheDocument();
  });

  it("shows unavailable message when status=unavailable", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ status: "unavailable", flagged: false, findings: [], context: [], detail: "" }),
        { headers: { "Content-Type": "application/json" } }
      )
    );

    render(<ThreatIntelPanel url={TEST_URL} />);

    await waitFor(() =>
      expect(
        screen.getByText(/No threat-intel sources returned a result/i)
      ).toBeInTheDocument()
    );
  });
});

import type { TicketReport } from "./types";
import { mockReport } from "./data/mockReport";

/**
 * Set to `true` to call the real backend endpoint; while the backend is still
 * being built, the mock report is returned after a short simulated delay.
 */
const USE_BACKEND = false;

const AUDIT_ENDPOINT = "/api/audit";

/**
 * Request a fraud audit for a ticket listing URL.
 *
 * @param url The full ticket listing URL to audit.
 * @returns The aggregated TicketReport.
 */
export async function auditUrl(url: string): Promise<TicketReport> {
  if (!USE_BACKEND) {
    // Simulate the ~30s backend analysis with a short delay for the demo.
    await new Promise((resolve) => setTimeout(resolve, 2200));
    return { ...mockReport, url };
  }

  const response = await fetch(AUDIT_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });

  if (!response.ok) {
    throw new Error(`Audit failed (${response.status})`);
  }

  return (await response.json()) as TicketReport;
}

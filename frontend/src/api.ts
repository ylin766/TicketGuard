import type { SecurityAuditResponse, TicketReport } from "./types";
import { scoreToVerdict } from "./types";
import { mockReport } from "./data/mockReport";

/**
 * Set to `true` to call the real backend endpoint; while the backend is still
 * being built, the mock report is returned after a short simulated delay.
 *
 * Defaults on, overridable via `VITE_USE_BACKEND=false` for offline demos.
 */
const USE_BACKEND = import.meta.env.VITE_USE_BACKEND !== "false";

const AUDIT_ENDPOINT =
  import.meta.env.VITE_AUDIT_ENDPOINT ??
  "http://localhost:8001/api/security/audit";

/**
 * Merge the live security audit into a display-ready TicketReport.
 *
 * The `/api/security/audit` endpoint only returns the credibility/threat layer,
 * so ticket metadata (match, venue, seat, price) is sourced from the mock
 * report as a placeholder while the real `websiteCredibility` dimension, the
 * overall score, verdict and recommendation come from the backend.
 */
function mergeAudit(url: string, audit: SecurityAuditResponse): TicketReport {
  const verdict = scoreToVerdict(audit.score);
  const recommendation =
    verdict === "danger"
      ? "High fraud risk — do not purchase from this listing."
      : verdict === "caution"
        ? "Proceed with caution and verify the seller independently."
        : "No major red flags detected — looks legitimate.";

  return {
    ...mockReport,
    url,
    overallScore: audit.score,
    verdict,
    recommendation,
    dimensions: {
      ...mockReport.dimensions,
      websiteCredibility: {
        score: audit.score,
        flags: audit.findings
          .filter((f) => f.threat === true)
          .map((f) => f.name),
        detail: audit.score_explanation || audit.detail,
      },
    },
    security: audit,
  };
}

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

  const audit = (await response.json()) as SecurityAuditResponse;
  return mergeAudit(url, audit);
}


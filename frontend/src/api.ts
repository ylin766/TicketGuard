import type { SecurityAuditResponse, TicketReport } from "./types";
import { scoreToVerdict } from "./types";
import { mockReport } from "./data/mockReport";
import type { ThreatScanCache } from "./components/ThreatIntelPanel";
import type { AgentState } from "./components/agent/useAgentStream";

/**
 * Merge the live security audit into a display-ready TicketReport.
 *
 * The audit only carries the credibility/threat layer, so ticket metadata
 * (match, venue, seat, price) is sourced from the mock report as a placeholder
 * while the real `websiteCredibility` dimension, the overall score, verdict and
 * recommendation come from the live data.
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
 * Assemble the display-ready report ENTIRELY from data already gathered during
 * the pipeline phase — the threat-intel scan cache plus the (grey-zone) opinion
 * agent trace. The report page is therefore purely presentational: it runs no
 * backend calls. Each backend source is queried exactly once, while the live
 * pipeline streams, and its result is reused here.
 *
 * @param url   The audited listing URL.
 * @param threat The completed threat-intel scan cache (sources + score).
 * @param agent  The opinion agent trace, when the grey zone escalated; else null.
 */
export function buildReportFromCache(
  url: string,
  threat: ThreatScanCache,
  agent: AgentState | null,
): TicketReport {
  const findings = threat.sources.filter((s) => s.threat !== null);
  const context = threat.sources.filter((s) => s.threat === null);
  const audit: SecurityAuditResponse = {
    status: "ok",
    flagged: threat.flagged,
    findings,
    context,
    detail: threat.sources
      .map((s) => s.detail)
      .filter(Boolean)
      .join(" "),
    // The opinion agent never changes the score (it only adds context), so the
    // scan's authoritative score is the final report score.
    score: threat.score ?? 50,
    risk_level: threat.riskLevel,
    score_explanation: threat.scoreExplanation,
    grey_zone: threat.greyZone,
    phoenix_url: agent?.phoenixUrl ?? null,
    agent_audit: agent
      ? { status: agent.status === "error" ? "error" : "ok" }
      : undefined,
  };
  return mergeAudit(url, audit);
}


import { motion } from "framer-motion";
import type { TicketReport } from "../types";
import type { ThreatScanCache } from "./ThreatIntelPanel";
import type { AgentState } from "./agent/useAgentStream";
import { RiskGauge } from "./RiskGauge";
import { ScoreCard } from "./ScoreCard";
import { ThreatIntelPanel } from "./ThreatIntelPanel";
import { AgentPanel } from "./agent/AgentPanel";
import "./ReportScreen.css";

interface ReportScreenProps {
  report: TicketReport;
  /** Return to the URL input screen. */
  onBack: () => void;
  /** Cached threat-intel sources from the pipeline phase — skip re-fetching. */
  threatCache?: ThreatScanCache;
  /** Cached AGENT agent trace from the pipeline phase. */
  agentCache?: AgentState;
}

const VERDICT_EMOJI = {
  safe: "✅",
  caution: "⚠️",
  danger: "🚫",
} as const;

function formatUsd(value: number): string {
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

export function ReportScreen({
  report,
  onBack,
  threatCache,
  agentCache,
}: ReportScreenProps) {
  const { dimensions } = report;
  const markup = Math.round(
    ((report.listingPrice - report.marketMedian) / report.marketMedian) * 100
  );

  return (
    <motion.div
      className="report-screen"
      initial={{ opacity: 0, y: 26 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -26 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="report-topbar">
        <button className="back-button neu-raised" onClick={onBack} type="button">
          <span aria-hidden="true">←</span> New Audit
        </button>
        <span className="topbar-badge glass">
          Pre-purchase Report
        </span>
      </div>

      <div className="report-grid">
        {/* Left Column: Main Analysis */}
        <div className="report-col-main">
          <header className="report-hero clay">
            <div className="report-hero-main">
              <span className="eyebrow">Audited listing</span>
              <p className="report-url">{report.url}</p>
              <h2 className="report-match">{report.match}</h2>
              <p className="report-venue muted">
                {report.venue} · Sec {report.seat.section} · Row {report.seat.row} ·
                Seat {report.seat.seat}
              </p>

              <div className="report-prices">
                <div className="price-pill neu-inset">
                  <span className="eyebrow">Listing</span>
                  <strong>{formatUsd(report.listingPrice)}</strong>
                </div>
                <div className="price-pill neu-inset">
                  <span className="eyebrow">Market median</span>
                  <strong>{formatUsd(report.marketMedian)}</strong>
                </div>
                <div className="price-pill neu-inset">
                  <span className="eyebrow">Markup</span>
                  <strong className={markup > 20 ? "text-danger" : "text-safe"}>
                    {markup > 0 ? "+" : ""}
                    {markup}%
                  </strong>
                </div>
              </div>
            </div>
          </header>

          <div className={`recommendation glass verdict-${report.verdict}`}>
            <span className="recommendation-emoji" aria-hidden="true">
              {VERDICT_EMOJI[report.verdict]}
            </span>
            <p className="recommendation-text">{report.recommendation}</p>
          </div>

          <section className="score-grid">
            <ScoreCard
              icon="🌐"
              title="Website credibility"
              weight="40%"
              result={dimensions.websiteCredibility}
            />
            <ScoreCard
              icon="💰"
              title="Fair price"
              weight="25%"
              result={dimensions.price}
            />
            <ScoreCard
              icon="⚖️"
              title="Legal compliance"
              weight="20%"
              result={dimensions.compliance}
            />
            <ScoreCard
              icon="👁️"
              title="Sightline"
              weight="15%"
              result={dimensions.sightline}
            />
          </section>

          {agentCache && (
            <AgentPanel state={agentCache} variant="report" />
          )}
        </div>

        {/* Right Column: Assessment & Intel */}
        <div className="report-col-side">
          <div className="report-gauge-card clay">
            <span className="eyebrow">Trust Assessment</span>
            <RiskGauge score={report.overallScore} verdict={report.verdict} />
          </div>

          <ThreatIntelPanel
            url={report.url}
            cachedSources={threatCache?.sources}
            cachedFlagged={threatCache?.flagged}
          />
        </div>
      </div>
    </motion.div>
  );
}

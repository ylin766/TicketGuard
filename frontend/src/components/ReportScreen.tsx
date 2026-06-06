import { motion } from "framer-motion";
import type { TicketReport } from "../types";
import { RiskGauge } from "./RiskGauge";
import { ScoreCard } from "./ScoreCard";
import { ThreatIntelPanel } from "./ThreatIntelPanel";
import "./ReportScreen.css";

interface ReportScreenProps {
  report: TicketReport;
  /** Return to the URL input screen. */
  onBack: () => void;
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

export function ReportScreen({ report, onBack }: ReportScreenProps) {
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
          <span aria-hidden="true">←</span> Back
        </button>
        <span className="eyebrow">Pre-purchase report</span>
      </div>

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

        <div className="report-hero-gauge">
          <RiskGauge score={report.overallScore} verdict={report.verdict} />
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

      <ThreatIntelPanel url={report.url} />

      <button className="report-footer-back neu-raised" onClick={onBack} type="button">
        ← Audit another listing
      </button>
    </motion.div>
  );
}

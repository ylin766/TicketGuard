import { motion } from "framer-motion";
import type { TicketReport } from "../types";
import type { ThreatScanCache } from "./ThreatIntelPanel";
import type { AgentState } from "./agent/useAgentStream";
import { RiskGauge } from "./RiskGauge";
import { ScoreCard } from "./ScoreCard";
import { ThreatIntelPanel } from "./ThreatIntelPanel";
import { AgentPanel } from "./agent/AgentPanel";
import { AgentBrowserViewport } from "./agent/AgentBrowserViewport";
import type { BrowserCheckState } from "./agent/useBrowserCheckStream";
import { LiveBrowserViewport } from "./price/LiveBrowserViewport";
import { PriceAnalysisPanel } from "./price/PriceAnalysisPanel";
import type { PriceState } from "./price/usePriceStream";
import "./ReportScreen.css";

interface ReportScreenProps {
  report: TicketReport;
  /** Return to the URL input screen. */
  onBack: () => void;
  /** Cached threat-intel sources from the pipeline phase — skip re-fetching. */
  threatCache?: ThreatScanCache;
  /** Cached AGENT agent trace from the pipeline phase. */
  agentCache?: AgentState;
  /** Cached Layer-2 browser-probe findings (brand check + sensitive surfaces). */
  browserCache?: BrowserCheckState;
  /** Live/finished price stream state, owned by App (ran during the pipeline). */
  price: PriceState;
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

function formatMoney(value: number, currency = "USD"): string {
  try {
    return value.toLocaleString("en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    });
  } catch {
    return `${value.toLocaleString("en-US", { maximumFractionDigits: 0 })} ${currency}`;
  }
}

export function ReportScreen({
  report,
  onBack,
  threatCache,
  agentCache,
  browserCache,
  price,
}: ReportScreenProps) {
  const { dimensions } = report;
  // Prefer the LIVE data gathered during the pipeline (vision-extracted from the
  // buyer's own page + the live market scrape) over the mock placeholders; fall
  // back to the report's values only when a field wasn't extracted.
  const ul = price.userListing;
  const match = ul?.event_name || report.match;
  const venue = ul?.venue || report.venue;
  const section = ul?.section || report.seat.section;
  const row = ul?.row || report.seat.row;
  const seat = ul?.seat || report.seat.seat;
  const listingPrice = ul?.price_per_ticket ?? report.listingPrice;
  const marketMedian = price.median ?? report.marketMedian;
  const markup = Math.round(
    ((listingPrice - marketMedian) / marketMedian) * 100
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

      {/* Header band: listing identity (wide) paired with the trust gauge
          (narrow) — an intentionally asymmetric headline zone. */}
      <div className="report-headband">
        <header className="report-hero clay">
          <div className="report-hero-main">
            <span className="eyebrow">Audited listing</span>
            <p className="report-url">{report.url}</p>
            <h2 className="report-match">{match}</h2>
            <p className="report-venue muted">
              {venue} · Sec {section} · Row {row} ·
              Seat {seat}
            </p>

            <div className="report-prices">
              <div className="price-pill neu-inset">
                <span className="eyebrow">Listing</span>
                <strong>{formatUsd(listingPrice)}</strong>
              </div>
              <div className="price-pill neu-inset">
                <span className="eyebrow">Market median</span>
                <strong>{formatMoney(marketMedian, price.currency)}</strong>
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

        <div className="report-gauge-card clay">
          <span className="eyebrow">Trust Assessment</span>
          <RiskGauge score={report.overallScore} verdict={report.verdict} />
          {threatCache?.deductions && threatCache.deductions.length > 0 ? (
            <ul className="gauge-why-list">
              {threatCache.deductions.map((d, i) => (
                <li key={`${d.label}-${i}`}>
                  <span className="gauge-why-label">{d.label}</span>
                  <span className="gauge-why-pts">−{d.points}</span>
                </li>
              ))}
            </ul>
          ) : (
            report.security?.score_explanation && (
              <p className="gauge-why">{report.security.score_explanation}</p>
            )
          )}
          {report.security?.phoenix_url && (
            <a
              className="phoenix-link"
              href={report.security.phoenix_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              View agent trace ↗
            </a>
          )}
        </div>
      </div>

      {/* Verdict — full-width divider between the headline and the detail. */}
      <div className={`recommendation glass verdict-${report.verdict}`}>
        <span className="recommendation-emoji" aria-hidden="true">
          {VERDICT_EMOJI[report.verdict]}
        </span>
        <p className="recommendation-text">{report.recommendation}</p>
      </div>

      {/* Body: analysis reading column + intel rail. */}
      <div className="report-body">
        <div className="report-col-main">
          <section className="score-grid score-grid--single">
            <ScoreCard
              icon="🌐"
              title="Website credibility"
              weight="Primary signal"
              result={dimensions.websiteCredibility}
            />
          </section>

          {agentCache && <AgentPanel state={agentCache} variant="report" />}

          {browserCache && (
            <AgentBrowserViewport state={browserCache} layout="split" />
          )}
        </div>

        <div className="report-col-side">
          <LiveBrowserViewport state={price} />

          <PriceAnalysisPanel state={price} />
        </div>
      </div>

      {/* Threat intelligence — full width so the per-source cards lay out in a
          compact multi-column grid instead of one tall stack in the rail. */}
      <ThreatIntelPanel
        url={report.url}
        cachedSources={threatCache?.sources}
        cachedFlagged={threatCache?.flagged}
      />
    </motion.div>
  );
}

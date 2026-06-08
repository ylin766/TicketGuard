import type { ThreatSource } from "../../types";
import {
  num,
  str,
  strList,
  bool,
  domainAge,
  waybackDate,
} from "./fields";
import { glyphForSource, GlyphCheck, GlyphAlert, GlyphInfo } from "./icons";
import "./SourcePanel.css";

/**
 * Per-source clay sub-panels. Every source shares one clay shell (icon, name,
 * verdict pip, detail) but renders a source-specific micro-visualization of its
 * native fields via a small registry keyed by source name.
 */

type Verdict = "danger" | "safe" | "info";

function verdictOf(source: ThreatSource): Verdict {
  if (source.threat === true) return "danger";
  if (source.threat === false) return "safe";
  return "info";
}

function VerdictPip({ verdict }: { verdict: Verdict }) {
  if (verdict === "danger") return <GlyphAlert className="ti-pip ti-pip--danger" />;
  if (verdict === "safe") return <GlyphCheck className="ti-pip ti-pip--safe" />;
  return <GlyphInfo className="ti-pip ti-pip--info" />;
}

/* ---------- Reusable micro-visualizations ---------- */

/** A clay ratio bar, e.g. "7 / 91 engines" with a colored fill. */
function RatioBar({
  hit,
  total,
  unit,
  danger,
}: {
  hit: number;
  total: number;
  unit: string;
  danger: boolean;
}) {
  const pct = total > 0 ? Math.min(100, Math.max(0, (hit / total) * 100)) : 0;
  // A non-zero hit should always show a sliver.
  const width = hit > 0 ? Math.max(4, pct) : 0;
  return (
    <div className="ti-ratio">
      <div className="ti-ratio-head">
        <span className="ti-ratio-num">
          <strong className={danger ? "text-danger" : "text-safe"}>{hit}</strong>
          <span className="ti-ratio-sep"> / {total}</span>
        </span>
        <span className="ti-ratio-unit">{unit}</span>
      </div>
      <div className="ti-ratio-track">
        <div
          className={`ti-ratio-fill ${danger ? "ti-ratio-fill--danger" : "ti-ratio-fill--safe"}`}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

/** A row of small clay chips. */
function Chips({ items, tone }: { items: string[]; tone: Verdict }) {
  if (items.length === 0) return null;
  return (
    <div className="ti-chips">
      {items.map((it) => (
        <span key={it} className={`ti-chip ti-chip--${tone}`}>
          {it.replace(/_/g, " ").toLowerCase()}
        </span>
      ))}
    </div>
  );
}

/** A single big stat with a caption, e.g. domain age. */
function Stat({ value, caption, tone }: { value: string; caption: string; tone?: Verdict }) {
  return (
    <div className="ti-stat">
      <span className={`ti-stat-value${tone ? ` ti-stat-value--${tone}` : ""}`}>{value}</span>
      <span className="ti-stat-caption">{caption}</span>
    </div>
  );
}

/* ---------- Source-specific bodies ---------- */

function EngineRatioBody({ source }: { source: ThreatSource }) {
  const malicious = num(source, "malicious") ?? num(source, "detected_by") ?? 0;
  const suspicious = num(source, "suspicious") ?? 0;
  const total = num(source, "total");
  const hit = malicious + suspicious;
  if (total === null) return null;
  return <RatioBar hit={hit} total={total} unit="engines" danger={hit > 0} />;
}

function ThreatTypesBody({ source }: { source: ThreatSource }) {
  const types = strList(source, "threat_types");
  if (types.length === 0) return null;
  return <Chips items={types} tone="danger" />;
}

function SucuriBody({ source }: { source: ThreatSource }) {
  const blacklists = strList(source, "blacklisted_by");
  const malware = bool(source, "malware");
  if (blacklists.length === 0 && !malware) return null;
  const items = malware ? [...blacklists, "malware"] : blacklists;
  return <Chips items={items} tone="danger" />;
}

function DispositionBody({ source }: { source: ThreatSource }) {
  const disposition = str(source, "disposition");
  if (!disposition) return null;
  const danger = source.threat === true;
  return (
    <span className={`ti-tag ti-tag--${danger ? "danger" : "safe"}`}>{disposition}</span>
  );
}

function MatchCountBody({ source }: { source: ThreatSource }) {
  const count = num(source, "match_count");
  if (count === null || count === 0) return null;
  return <Stat value={String(count)} caption="phishing records" tone="danger" />;
}

function RankBody({ source }: { source: ThreatSource }) {
  const rank = num(source, "rank");
  if (rank === null) {
    return <Stat value="unranked" caption="Tranco popularity" tone="info" />;
  }
  return <Stat value={`#${rank.toLocaleString()}`} caption="Tranco popularity" tone="safe" />;
}

function DomainAgeBody({ source }: { source: ThreatSource }) {
  const age = domainAge(str(source, "registered_on"));
  const statuses = strList(source, "status");
  return (
    <div className="ti-stack">
      {age ? (
        <Stat
          value={age.label}
          caption="domain age"
          tone={age.years >= 1 ? "safe" : "danger"}
        />
      ) : null}
      {statuses.length > 0 ? <Chips items={statuses} tone="info" /> : null}
    </div>
  );
}

function IpGeoBody({ source }: { source: ThreatSource }) {
  const country = str(source, "country");
  const ip = str(source, "ip");
  const isp = str(source, "isp");
  return (
    <div className="ti-kv">
      {country ? (
        <span className="ti-kv-item">
          <span className="ti-kv-key">country</span>
          <span className="ti-kv-val">{country}</span>
        </span>
      ) : null}
      {ip ? (
        <span className="ti-kv-item">
          <span className="ti-kv-key">ip</span>
          <span className="ti-kv-val">{ip}</span>
        </span>
      ) : null}
      {isp ? (
        <span className="ti-kv-item">
          <span className="ti-kv-key">isp</span>
          <span className="ti-kv-val">{isp}</span>
        </span>
      ) : null}
    </div>
  );
}

function WaybackBody({ source }: { source: ThreatSource }) {
  const has = bool(source, "has_snapshot");
  const date = waybackDate(str(source, "closest_timestamp"));
  if (has && date) return <Stat value={date} caption="oldest snapshot" tone="safe" />;
  return <Stat value="none" caption="web archive" tone="danger" />;
}

/** Registry: source name → body renderer. Missing → no body (detail only). */
const BODY_REGISTRY: Record<string, (p: { source: ThreatSource }) => JSX.Element | null> = {
  VirusTotal: EngineRatioBody,
  MetaDefender: EngineRatioBody,
  SafeBrowsing: ThreatTypesBody,
  Sucuri: SucuriBody,
  CheckPhish: DispositionBody,
  PhishStats: MatchCountBody,
  Tranco: RankBody,
  RDAP: DomainAgeBody,
  IPGeo: IpGeoBody,
  Wayback: WaybackBody,
};

export function SourcePanel({ source }: { source: ThreatSource }) {
  const verdict = verdictOf(source);
  const Glyph = glyphForSource(source.name);
  const Body = BODY_REGISTRY[source.name];

  return (
    <div className={`ti-spanel ti-spanel--${verdict}`}>
      <div className="ti-spanel-head">
        <span className="ti-spanel-glyph-wrap">
          <Glyph />
        </span>
        <span className="ti-spanel-name">{source.name}</span>
        <VerdictPip verdict={verdict} />
      </div>
      {Body ? (
        <div className="ti-spanel-body">
          <Body source={source} />
        </div>
      ) : null}
      <p className="ti-spanel-detail">{source.detail}</p>
    </div>
  );
}

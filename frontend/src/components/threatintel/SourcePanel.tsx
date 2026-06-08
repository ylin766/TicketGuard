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
import { themeClass } from "./theme";
import { loaderForSource } from "./loaders";
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

/**
 * A "clean vs threat" proportion bar. The track is ALWAYS full: the share of
 * engines that flagged a threat shows as a red segment, the rest as green. This
 * way "0 threats" reads as a reassuring full-green bar instead of an empty one.
 */
function RatioBar({
  hit,
  total,
  unit,
}: {
  hit: number;
  total: number;
  unit: string;
}) {
  const safeCount = Math.max(0, total - hit);
  const hitPct = total > 0 ? Math.min(100, Math.max(0, (hit / total) * 100)) : 0;
  // Give any non-zero hit a visible minimum so a single detection isn't invisible.
  const dangerWidth = hit > 0 ? Math.max(6, hitPct) : 0;
  const allClear = hit === 0;

  return (
    <div className="ti-ratio">
      <div className="ti-ratio-head">
        {allClear ? (
          <span className="ti-ratio-num">
            <strong className="text-safe">{total}</strong>
            <span className="ti-ratio-sep"> clear</span>
          </span>
        ) : (
          <span className="ti-ratio-num">
            <strong className="text-danger">{hit}</strong>
            <span className="ti-ratio-sep"> flagged · {safeCount} clear</span>
          </span>
        )}
        <span className="ti-ratio-unit">{unit}</span>
      </div>
      <div className="ti-ratio-track">
        <div
          className="ti-ratio-seg ti-ratio-seg--danger"
          style={{ width: `${dangerWidth}%` }}
        />
        <div className="ti-ratio-seg ti-ratio-seg--safe" style={{ flex: 1 }} />
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
  return <RatioBar hit={hit} total={total} unit="engines" />;
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
  // Render the body up front: several body renderers return null when their
  // fields are empty (e.g. a clean SafeBrowsing has no threat types). Only when
  // the body actually produces content do we reserve space for it — otherwise
  // the card is detail-only and centers its single line.
  const bodyContent = Body ? Body({ source }) : null;
  const hasBody = bodyContent != null;

  return (
    <div
      className={`ti-spanel ti-spanel--${verdict} ${themeClass(source.name)}${
        hasBody ? "" : " ti-spanel--detail-only"
      }`}
    >
      <div className="ti-spanel-head">
        <span className="ti-spanel-glyph-wrap">
          <Glyph />
        </span>
        <span className="ti-spanel-name">{source.name}</span>
        <VerdictPip verdict={verdict} />
      </div>
      {hasBody ? <div className="ti-spanel-body">{bodyContent}</div> : null}
      <p className="ti-spanel-detail">{source.detail}</p>
    </div>
  );
}

/**
 * Timeout panel — a source that was expected but never returned (e.g. it timed
 * out or errored server-side). We keep its slot instead of silently removing
 * the skeleton, so the user isn't confused by a card that appears then vanishes.
 */
export function SourcePanelTimeout({ name }: { name: string }) {
  const Glyph = glyphForSource(name);
  return (
    <div
      className={`ti-spanel ti-spanel--timeout ti-spanel--detail-only ${themeClass(name)}`}
    >
      <div className="ti-spanel-head">
        <span className="ti-spanel-glyph-wrap">
          <Glyph />
        </span>
        <span className="ti-spanel-name">{name}</span>
        <span className="ti-spanel-tag">timed out</span>
      </div>
      <p className="ti-spanel-detail">No response in time — source skipped.</p>
    </div>
  );
}

/**
 * Pending skeleton shown while a source's result is still streaming in. Keeps
 * the same footprint as the real panel (stable layout) and shows the source's
 * themed glyph plus a category-tinted looping loader for slow sources.
 */
export function SourcePanelSkeleton({ name }: { name: string }) {
  const Glyph = glyphForSource(name);
  const Loader = loaderForSource(name);
  return (
    <div
      className={`ti-spanel ti-spanel--pending ${themeClass(name)}`}
      aria-busy="true"
      aria-label={`${name} loading`}
    >
      <div className="ti-spanel-head">
        <span className="ti-spanel-glyph-wrap">
          <Glyph />
        </span>
        <span className="ti-spanel-name">{name}</span>
        <span className="ti-spanel-loader">
          <Loader />
        </span>
      </div>
      <div className="ti-spanel-body">
        <span className="ti-skeleton-line ti-skeleton-line--lg" />
        <span className="ti-skeleton-line" />
      </div>
    </div>
  );
}

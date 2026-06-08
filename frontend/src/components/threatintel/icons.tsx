/**
 * Clay-compatible line-art icons for each threat-intel source and for the
 * shared verdict states. All icons are stroke-based, inherit `currentColor`,
 * and share the `.ti-glyph` sizing class — no emoji anywhere.
 */

interface GlyphProps {
  className?: string;
}

function Svg({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <svg
      className={`ti-glyph${className ? ` ${className}` : ""}`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

/* ---------- Verdict / status glyphs ---------- */

export function GlyphShield({ className }: GlyphProps) {
  return (
    <Svg className={className}>
      <path d="M12 2L4 6v6c0 5.25 3.5 10.15 8 11.35C16.5 22.15 20 17.25 20 12V6L12 2z" />
    </Svg>
  );
}

export function GlyphCheck({ className }: GlyphProps) {
  return (
    <Svg className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12l3 3 5-5" strokeWidth="2" />
    </Svg>
  );
}

export function GlyphAlert({ className }: GlyphProps) {
  return (
    <Svg className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v4M12 16h.01" strokeWidth="2" />
    </Svg>
  );
}

export function GlyphInfo({ className }: GlyphProps) {
  return (
    <Svg className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5M12 8h.01" strokeWidth="2" />
    </Svg>
  );
}

/* ---------- Per-source glyphs ---------- */

/** VirusTotal — many engines / radial scan. */
export function GlyphEngines({ className }: GlyphProps) {
  return (
    <Svg className={className}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" />
    </Svg>
  );
}

/** Safe Browsing — browser window with a shielded mark. */
export function GlyphBrowser({ className }: GlyphProps) {
  return (
    <Svg className={className}>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <path d="M3 9h18M7 6.5h.01M10 6.5h.01" />
    </Svg>
  );
}

/** URLhaus / OpenPhish — feed / list of entries. */
export function GlyphFeed({ className }: GlyphProps) {
  return (
    <Svg className={className}>
      <path d="M4 7h16M4 12h16M4 17h10" />
    </Svg>
  );
}

/** CheckPhish — hook (phishing). */
export function GlyphHook({ className }: GlyphProps) {
  return (
    <Svg className={className}>
      <path d="M16 4v9a5 5 0 0 1-10 0" />
      <circle cx="16" cy="3.5" r="1.4" />
    </Svg>
  );
}

/** MetaDefender — layered shield / multi-engine reputation. */
export function GlyphLayers({ className }: GlyphProps) {
  return (
    <Svg className={className}>
      <path d="M12 3l8 4-8 4-8-4 8-4z" />
      <path d="M4 12l8 4 8-4M4 16.5l8 4 8-4" />
    </Svg>
  );
}

/** Sucuri — bug / malware. */
export function GlyphBug({ className }: GlyphProps) {
  return (
    <Svg className={className}>
      <rect x="8" y="8" width="8" height="10" rx="4" />
      <path d="M12 5v3M9 4l2 2M15 4l-2 2M5 11h3M16 11h3M5 16h3M16 16h3" />
    </Svg>
  );
}

/** PhishStats — bar chart / counts. */
export function GlyphChart({ className }: GlyphProps) {
  return (
    <Svg className={className}>
      <path d="M4 20V10M10 20V4M16 20v-7M21 20H3" />
    </Svg>
  );
}

/** Tranco — trophy / popularity rank. */
export function GlyphRank({ className }: GlyphProps) {
  return (
    <Svg className={className}>
      <path d="M7 4h10v3a5 5 0 0 1-10 0V4z" />
      <path d="M5 5H4a2 2 0 0 0 2 3M19 5h1a2 2 0 0 1-2 3M9 14h6M10 20h4M12 14v6" />
    </Svg>
  );
}

/** Wayback — archival history / clock arrow. */
export function GlyphHistory({ className }: GlyphProps) {
  return (
    <Svg className={className}>
      <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
      <path d="M3 4v4h4M12 8v4l3 2" />
    </Svg>
  );
}

/** RDAP — calendar / registration date. */
export function GlyphCalendar({ className }: GlyphProps) {
  return (
    <Svg className={className}>
      <rect x="4" y="5" width="16" height="16" rx="2.5" />
      <path d="M4 10h16M9 3v4M15 3v4" />
    </Svg>
  );
}

/** IPGeo — globe / location. */
export function GlyphGlobe({ className }: GlyphProps) {
  return (
    <Svg className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.5 2.5 2.5 15 0 18M12 3c-2.5 2.5-2.5 15 0 18" />
    </Svg>
  );
}

/** Chevron used by the panel header. */
export function GlyphChevron({
  expanded,
  className,
}: GlyphProps & { expanded: boolean }) {
  return (
    <svg
      className={`ti-glyph ti-chevron${expanded ? " ti-chevron--up" : ""}${
        className ? ` ${className}` : ""
      }`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

/** Map a source name to its glyph (falls back to a generic info glyph). */
export function glyphForSource(name: string): (props: GlyphProps) => JSX.Element {
  switch (name) {
    case "VirusTotal":
      return GlyphEngines;
    case "SafeBrowsing":
      return GlyphBrowser;
    case "URLhaus":
    case "OpenPhish":
      return GlyphFeed;
    case "CheckPhish":
      return GlyphHook;
    case "MetaDefender":
      return GlyphLayers;
    case "Sucuri":
      return GlyphBug;
    case "PhishStats":
      return GlyphChart;
    case "Tranco":
      return GlyphRank;
    case "Wayback":
      return GlyphHistory;
    case "RDAP":
      return GlyphCalendar;
    case "IPGeo":
      return GlyphGlobe;
    default:
      return GlyphInfo;
  }
}

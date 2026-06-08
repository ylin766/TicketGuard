/**
 * Per-source clay color themes. Claymorphism lives on *color variety*, so each
 * threat-intel source gets its own soft, distinct clay hue (spread around the
 * color wheel and kept low-saturation so they stay on-brand and playful rather
 * than loud). The theme tints the whole sub-panel block (light background wash +
 * the colored icon glyph). It is independent from the verdict color (safe/
 * danger), which only ever shows on the small pip and on actual threat accents.
 *
 * Each source maps to a `ti-theme--<key>` CSS class defined in SourcePanel.css.
 */

export type ThemeKey =
  | "virustotal"
  | "safebrowsing"
  | "urlhaus"
  | "checkphish"
  | "metadefender"
  | "sucuri"
  | "openphish"
  | "phishstats"
  | "tranco"
  | "crtsh"
  | "wayback"
  | "rdap"
  | "ipgeo"
  | "default";

const THEME_BY_SOURCE: Record<string, ThemeKey> = {
  VirusTotal: "virustotal", // indigo
  SafeBrowsing: "safebrowsing", // sky blue
  URLhaus: "urlhaus", // coral
  CheckPhish: "checkphish", // teal
  MetaDefender: "metadefender", // violet
  Sucuri: "sucuri", // amber
  OpenPhish: "openphish", // rose
  PhishStats: "phishstats", // cyan
  Tranco: "tranco", // gold
  "crt.sh": "crtsh", // green
  Wayback: "wayback", // plum
  RDAP: "rdap", // slate blue
  IPGeo: "ipgeo", // mint
};

export function themeForSource(name: string): ThemeKey {
  return THEME_BY_SOURCE[name] ?? "default";
}

export function themeClass(name: string): string {
  return `ti-theme--${themeForSource(name)}`;
}

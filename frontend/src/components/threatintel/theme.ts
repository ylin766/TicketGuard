/**
 * Category color themes for threat-intel sources. The theme tints the *whole*
 * sub-panel block (icon well background + a top accent bar + any loader stroke)
 * so users can scan sources by family at a glance. This is independent from the
 * verdict color (safe/danger), which stays on the left border + pip.
 *
 * Each theme maps to a `ti-theme--<key>` CSS class defined in SourcePanel.css,
 * whose values are derived from the project's pitch-clay palette so the tints
 * stay soft and on-brand.
 */

export type ThemeKey = "malware" | "reputation" | "registry" | "network";

const THEME_BY_SOURCE: Record<string, ThemeKey> = {
  // Malicious detection engines — warm red/orange family.
  VirusTotal: "malware",
  SafeBrowsing: "malware",
  URLhaus: "malware",
  CheckPhish: "malware",
  MetaDefender: "malware",
  Sucuri: "malware",
  OpenPhish: "malware",
  PhishStats: "malware",
  // Reputation / popularity — golden family.
  Tranco: "reputation",
  // Domain / registration / history — violet family.
  RDAP: "registry",
  "crt.sh": "registry",
  Wayback: "registry",
  // Geo / network — teal family.
  IPGeo: "network",
};

export function themeForSource(name: string): ThemeKey {
  return THEME_BY_SOURCE[name] ?? "network";
}

export function themeClass(name: string): string {
  return `ti-theme--${themeForSource(name)}`;
}

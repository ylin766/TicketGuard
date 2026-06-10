import type { ThreatSource } from "../../types";

/**
 * Safe, typed accessors for the source-native fields that arrive on a
 * `ThreatSource` (everything beyond name/threat/detail is `unknown`). Each
 * helper narrows a single field and returns a sensible fallback so panels never
 * crash on a missing or malformed value.
 */

export function num(source: ThreatSource, key: string): number | null {
  const v = source[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function str(source: ThreatSource, key: string): string | null {
  const v = source[key];
  return typeof v === "string" && v.length > 0 ? v : null;
}

export function bool(source: ThreatSource, key: string): boolean | null {
  const v = source[key];
  return typeof v === "boolean" ? v : null;
}

export function strList(source: ThreatSource, key: string): string[] {
  const v = source[key];
  if (!Array.isArray(v)) return [];
  return v.filter((x): x is string => typeof x === "string" && x.length > 0);
}

/**
 * Compute a human-friendly domain age from an RDAP registration timestamp.
 * Returns null when the date is missing or unparseable.
 */
export function domainAge(
  registeredOn: string | null
): { years: number; label: string } | null {
  if (!registeredOn) return null;
  const then = new Date(registeredOn);
  if (Number.isNaN(then.getTime())) return null;

  const ms = Date.now() - then.getTime();
  if (ms < 0) return { years: 0, label: "brand new" };

  const days = Math.floor(ms / 86_400_000);
  const years = Math.floor(days / 365);
  const months = Math.floor((days % 365) / 30);

  if (years >= 1) {
    return { years, label: years === 1 ? "1 yr" : `${years} yrs` };
  }
  if (months >= 1) {
    return { years: 0, label: months === 1 ? "1 mo" : `${months} mos` };
  }
  return { years: 0, label: days <= 1 ? "today" : `${days} days` };
}

/** Format a Wayback timestamp (YYYYMMDDhhmmss) as YYYY-MM-DD, else null. */
export function waybackDate(ts: string | null): string | null {
  if (!ts || ts.length < 8) return null;
  return `${ts.slice(0, 4)}-${ts.slice(4, 6)}-${ts.slice(6, 8)}`;
}

import type { ThreatSource } from "../../types";

/**
 * Real-shape threat-intel fixtures, captured from an actual pipeline run so the
 * per-source panels can be developed and tested without a live backend.
 *
 * The "clean" set is a verbatim capture of `run_pipeline("http://example.com")`.
 * The "flagged" set mirrors the same source field shapes but with threat
 * verdicts, so danger-state rendering is exercised too.
 */

/** Clean run — every threat source returns threat=false, context is benign. */
export const CLEAN_SOURCES: ThreatSource[] = [
  {
    name: "VirusTotal",
    threat: false,
    malicious: 0,
    suspicious: 0,
    harmless: 63,
    total: 91,
    detail: "0 malicious / 0 suspicious of 91 engines.",
  },
  {
    name: "SafeBrowsing",
    threat: false,
    threat_types: [],
    detail: "No Safe Browsing match.",
  },
  { name: "URLhaus", threat: false, detail: "Not listed in URLhaus." },
  {
    name: "CheckPhish",
    threat: false,
    disposition: "clean",
    detail: "CheckPhish disposition: clean.",
  },
  {
    name: "MetaDefender",
    threat: false,
    detected_by: 0,
    total: 22,
    detail: "0 of 22 reputation engines detected a threat.",
  },
  {
    name: "Sucuri",
    threat: false,
    blacklisted_by: [],
    malware: false,
    detail: "No Sucuri blacklist or malware warning.",
  },
  {
    name: "OpenPhish",
    threat: false,
    detail: "Not on the OpenPhish feed (300 entries checked).",
  },
  {
    name: "PhishStats",
    threat: false,
    match_count: 0,
    detail: "No PhishStats record for example.com.",
  },
  {
    name: "Tranco",
    threat: null,
    rank: 180,
    detail: "example.com ranks #180 on the Tranco popularity list.",
  },
  {
    name: "Wayback",
    threat: null,
    has_snapshot: true,
    closest_timestamp: "20260607192750",
    detail: "Archived; closest snapshot 20260607192750.",
  },
  {
    name: "RDAP",
    threat: null,
    registered_on: "1995-08-14T04:00:00Z",
    status: [
      "client delete prohibited",
      "client transfer prohibited",
      "client update prohibited",
    ],
    detail: "Domain registered on 1995-08-14T04:00:00Z.",
  },
  {
    name: "IPGeo",
    threat: null,
    ip: "172.66.147.243",
    country: "Canada",
    isp: null,
    detail: "example.com resolves to 172.66.147.243 (Canada).",
  },
];

/** Flagged run — several threat sources fire, context shows a young domain. */
export const FLAGGED_SOURCES: ThreatSource[] = [
  {
    name: "VirusTotal",
    threat: true,
    malicious: 7,
    suspicious: 3,
    harmless: 51,
    total: 91,
    detail: "7 malicious / 3 suspicious of 91 engines.",
  },
  {
    name: "SafeBrowsing",
    threat: true,
    threat_types: ["SOCIAL_ENGINEERING", "MALWARE"],
    detail: "Safe Browsing matched: SOCIAL_ENGINEERING, MALWARE.",
  },
  {
    name: "URLhaus",
    threat: true,
    detail: "Listed in URLhaus (malware distribution).",
  },
  {
    name: "CheckPhish",
    threat: true,
    disposition: "phish",
    detail: "CheckPhish disposition: phish.",
  },
  {
    name: "MetaDefender",
    threat: true,
    detected_by: 4,
    total: 22,
    detail: "4 of 22 reputation engines detected a threat.",
  },
  {
    name: "Sucuri",
    threat: false,
    blacklisted_by: [],
    malware: false,
    detail: "No Sucuri blacklist or malware warning.",
  },
  {
    name: "OpenPhish",
    threat: true,
    detail: "On the OpenPhish feed.",
  },
  {
    name: "PhishStats",
    threat: true,
    match_count: 5,
    detail: "5 PhishStats records for this host.",
  },
  {
    name: "Tranco",
    threat: null,
    rank: null,
    detail: "Not ranked on the Tranco popularity list.",
  },
  {
    name: "Wayback",
    threat: null,
    has_snapshot: false,
    closest_timestamp: null,
    detail: "No archived snapshot found.",
  },
  {
    name: "RDAP",
    threat: null,
    registered_on: "2026-05-20T11:30:00Z",
    status: ["client transfer prohibited"],
    detail: "Domain registered on 2026-05-20T11:30:00Z.",
  },
  {
    name: "IPGeo",
    threat: null,
    ip: "45.133.1.99",
    country: "Russia",
    isp: "Hosting LLC",
    detail: "resolves to 45.133.1.99 (Russia).",
  },
];

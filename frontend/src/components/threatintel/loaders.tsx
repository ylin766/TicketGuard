/**
 * Per-source looping "waiting" animations for the slow threat-intel sources.
 * All are clay-styled, use `currentColor` (so they inherit the panel's category
 * theme tint), loop forever, and stop on `prefers-reduced-motion` (handled in
 * SourcePanel.css). Fast sources fall back to the shared breathing skeleton.
 */

interface LoaderProps {
  className?: string;
}

function Frame({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <svg
      className={`ti-loader${className ? ` ${className}` : ""}`}
      viewBox="0 0 48 48"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

/** VirusTotal — radial engine scan: a sweep arm rotates while the ring of
 *  engine dots light up in sequence as it passes (radar-style scan). */
export function LoaderRadialScan({ className }: LoaderProps) {
  const dots = Array.from({ length: 8 }, (_, i) => {
    const a = (i / 8) * Math.PI * 2;
    return { x: 24 + Math.cos(a) * 15, y: 24 + Math.sin(a) * 15, i };
  });
  return (
    <Frame className={`ti-loader--scan ${className ?? ""}`}>
      <circle cx="24" cy="24" r="5" className="ti-scan-core" />
      <line x1="24" y1="24" x2="24" y2="11" className="ti-scan-arm" />
      {dots.map((d) => (
        <circle
          key={d.i}
          cx={d.x}
          cy={d.y}
          r="2.4"
          fill="currentColor"
          stroke="none"
          className="ti-scan-dot"
          style={{ animationDelay: `${d.i * 0.18}s` }}
        />
      ))}
    </Frame>
  );
}

/** CheckPhish — a fishing hook swinging like a pendulum while it bobs. */
export function LoaderHookBob({ className }: LoaderProps) {
  return (
    <Frame className={`ti-loader--bob ${className ?? ""}`}>
      <g className="ti-bob-group">
        <path d="M30 10v14a8 8 0 0 1-16 0" />
        <circle cx="30" cy="9" r="2.2" fill="currentColor" stroke="none" />
      </g>
    </Frame>
  );
}

/** MetaDefender — three shield layers sweeping bright in sequence. */
export function LoaderLayerSweep({ className }: LoaderProps) {
  return (
    <Frame className={`ti-loader--sweep ${className ?? ""}`}>
      <path d="M24 8l14 6-14 6-14-6 14-6z" className="ti-sweep-layer" style={{ animationDelay: "0s" }} />
      <path d="M10 22l14 6 14-6" className="ti-sweep-layer" style={{ animationDelay: "0.18s" }} />
      <path d="M10 30l14 6 14-6" className="ti-sweep-layer" style={{ animationDelay: "0.36s" }} />
    </Frame>
  );
}

/** crt.sh — certificate seal drawing its outline on a loop. */
export function LoaderStrokeFlow({ className }: LoaderProps) {
  return (
    <Frame className={`ti-loader--flow ${className ?? ""}`}>
      <rect x="10" y="9" width="28" height="22" rx="3" className="ti-flow-path" />
      <circle cx="24" cy="36" r="5" className="ti-flow-path" style={{ animationDelay: "0.4s" }} />
    </Frame>
  );
}

/** Wayback — clock hand rewinding (rotating backwards). */
export function LoaderClockRewind({ className }: LoaderProps) {
  return (
    <Frame className={`ti-loader--clock ${className ?? ""}`}>
      <circle cx="24" cy="24" r="15" />
      <line x1="24" y1="24" x2="24" y2="14" className="ti-clock-hand" />
    </Frame>
  );
}

/** RDAP — calendar page flipping on a loop. */
export function LoaderPageFlip({ className }: LoaderProps) {
  return (
    <Frame className={`ti-loader--flip ${className ?? ""}`}>
      <rect x="10" y="11" width="28" height="26" rx="3" />
      <path d="M10 18h28M18 8v6M30 8v6" />
      <rect x="14" y="22" width="20" height="11" rx="1.5" className="ti-flip-page" />
    </Frame>
  );
}

/** A generic breathing pill for fast sources that need no special animation. */
export function LoaderBreathe({ className }: LoaderProps) {
  return <span className={`ti-loader-breathe${className ? ` ${className}` : ""}`} aria-hidden="true" />;
}

/** SafeBrowsing — a browser window with a scan line sweeping up and down. */
export function LoaderScanWindow({ className }: LoaderProps) {
  return (
    <Frame className={`ti-loader--win ${className ?? ""}`}>
      <rect x="9" y="11" width="30" height="26" rx="3" />
      <path d="M9 18h30" />
      <line x1="13" y1="27" x2="35" y2="27" className="ti-win-scan" />
    </Frame>
  );
}

/** URLhaus / OpenPhish — feed rows lighting up in sequence (streaming list). */
export function LoaderFeedStream({ className }: LoaderProps) {
  return (
    <Frame className={`ti-loader--feed ${className ?? ""}`}>
      <line x1="12" y1="16" x2="36" y2="16" className="ti-feed-line" style={{ animationDelay: "0s" }} />
      <line x1="12" y1="24" x2="36" y2="24" className="ti-feed-line" style={{ animationDelay: "0.18s" }} />
      <line x1="12" y1="32" x2="28" y2="32" className="ti-feed-line" style={{ animationDelay: "0.36s" }} />
    </Frame>
  );
}

/** Sucuri — a bug whose body bobs while its legs wiggle (crawling). */
export function LoaderBugCrawl({ className }: LoaderProps) {
  return (
    <Frame className={`ti-loader--bug ${className ?? ""}`}>
      <g className="ti-bug-legs">
        <path d="M18 21h-7M30 21h7M18 27h-7M30 27h7" />
      </g>
      <g className="ti-bug-body">
        <rect x="18" y="16" width="12" height="16" rx="6" />
        <path d="M24 12v4M21 11l3 3M27 11l-3 3" />
      </g>
    </Frame>
  );
}

/** PhishStats — three equalizer bars rising and falling (counts ticking). */
export function LoaderBars({ className }: LoaderProps) {
  return (
    <Frame className={`ti-loader--bars ${className ?? ""}`}>
      <rect x="11" y="14" width="6" height="24" rx="2" fill="currentColor" stroke="none" className="ti-bar" style={{ animationDelay: "0s" }} />
      <rect x="21" y="14" width="6" height="24" rx="2" fill="currentColor" stroke="none" className="ti-bar" style={{ animationDelay: "0.22s" }} />
      <rect x="31" y="14" width="6" height="24" rx="2" fill="currentColor" stroke="none" className="ti-bar" style={{ animationDelay: "0.44s" }} />
    </Frame>
  );
}

/** Tranco — a trophy that pulses and lifts (rank rising). */
export function LoaderTrophyPulse({ className }: LoaderProps) {
  return (
    <Frame className={`ti-loader--trophy ${className ?? ""}`}>
      <g className="ti-trophy">
        <path d="M16 12h16v5a8 8 0 0 1-16 0v-5z" />
        <path d="M16 13h-4a3 3 0 0 0 4 4M32 13h4a3 3 0 0 1-4 4" />
        <path d="M20 33h8M24 25v8" />
      </g>
    </Frame>
  );
}

/** IPGeo — a globe with a radar sweep hand rotating around it. */
export function LoaderRadar({ className }: LoaderProps) {
  return (
    <Frame className={`ti-loader--radar ${className ?? ""}`}>
      <circle cx="24" cy="24" r="15" />
      <path d="M9 24h30" className="ti-radar-grid" />
      <path d="M24 9c5.5 5 5.5 25 0 30M24 9c-5.5 5-5.5 25 0 30" className="ti-radar-grid" />
      <line x1="24" y1="24" x2="24" y2="9" className="ti-radar-sweep" />
    </Frame>
  );
}

/** Map a source name to its loader; fast sources get the breathing fallback. */
export function loaderForSource(name: string): (p: LoaderProps) => JSX.Element {
  switch (name) {
    case "VirusTotal":
      return LoaderRadialScan;
    case "SafeBrowsing":
      return LoaderScanWindow;
    case "URLhaus":
      return LoaderStrokeFlow; // Swapped with crt.sh
    case "OpenPhish":
      return LoaderFeedStream;
    case "CheckPhish":
      return LoaderHookBob;
    case "MetaDefender":
      return LoaderLayerSweep;
    case "Sucuri":
      return LoaderBugCrawl;
    case "PhishStats":
      return LoaderPageFlip; // Swapped with RDAP
    case "Tranco":
      return LoaderTrophyPulse;
    case "crt.sh":
      return LoaderFeedStream; // Swapped with URLhaus
    case "Wayback":
      return LoaderClockRewind;
    case "RDAP":
      return LoaderBars; // Swapped with PhishStats
    case "IPGeo":
      return LoaderRadar;
    default:
      return LoaderBreathe;
  }
}

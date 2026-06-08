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

/** VirusTotal — radial engine scan: outer dots light up around a core. */
export function LoaderRadialScan({ className }: LoaderProps) {
  const dots = Array.from({ length: 8 }, (_, i) => {
    const a = (i / 8) * Math.PI * 2;
    return { x: 24 + Math.cos(a) * 15, y: 24 + Math.sin(a) * 15, i };
  });
  return (
    <Frame className={`ti-loader--scan ${className ?? ""}`}>
      <circle cx="24" cy="24" r="5" className="ti-scan-core" />
      {dots.map((d) => (
        <circle
          key={d.i}
          cx={d.x}
          cy={d.y}
          r="2.4"
          fill="currentColor"
          stroke="none"
          className="ti-scan-dot"
          style={{ animationDelay: `${d.i * 0.12}s` }}
        />
      ))}
    </Frame>
  );
}

/** CheckPhish — fishing hook bobbing up and down. */
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

/** Map a source name to its loader; fast sources get the breathing fallback. */
export function loaderForSource(name: string): (p: LoaderProps) => JSX.Element {
  switch (name) {
    case "VirusTotal":
      return LoaderRadialScan;
    case "CheckPhish":
      return LoaderHookBob;
    case "MetaDefender":
      return LoaderLayerSweep;
    case "crt.sh":
      return LoaderStrokeFlow;
    case "Wayback":
      return LoaderClockRewind;
    case "RDAP":
      return LoaderPageFlip;
    default:
      return LoaderBreathe;
  }
}

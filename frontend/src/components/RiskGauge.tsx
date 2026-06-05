import type { Verdict } from "../types";

interface RiskGaugeProps {
  /** 0–100 score. */
  score: number;
  verdict: Verdict;
  /** Pixel diameter of the gauge. */
  size?: number;
}

const VERDICT_COLOR: Record<Verdict, string> = {
  safe: "#2bb673",
  caution: "#e8a13a",
  danger: "#e5484d",
};

const VERDICT_LABEL: Record<Verdict, string> = {
  safe: "Looks safe",
  caution: "Proceed with caution",
  danger: "High risk",
};

/** A circular neumorphic progress gauge for the overall risk score. */
export function RiskGauge({ score, verdict, size = 184 }: RiskGaugeProps) {
  const stroke = 16;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, score));
  const offset = circumference * (1 - clamped / 100);
  const color = VERDICT_COLOR[verdict];

  return (
    <div
      className={`risk-gauge risk-gauge--${verdict}`}
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size}>
        <defs>
          {/* Claymorphic raised ring (recipe: soft directional shading for the
              rounded bead + a bright inner top highlight, the hallmark of clay).
              Every layer is clipped INTO the stroke so nothing spills outside. */}
          <filter
            id={`ring-emboss-${verdict}`}
            x="-25%"
            y="-25%"
            width="150%"
            height="150%"
            colorInterpolationFilters="sRGB"
          >
            <feGaussianBlur in="SourceAlpha" stdDeviation="4" result="bump" />
            <feDiffuseLighting
              in="bump"
              surfaceScale="2.6"
              diffuseConstant="1"
              lightingColor="#ffffff"
              result="diff"
            >
              <feDistantLight azimuth="235" elevation="62" />
            </feDiffuseLighting>
            <feComposite in="diff" in2="SourceAlpha" operator="in" result="diffClip" />
            {/* Multiply the shading onto the colored ring. Multiply can only
                darken, so the base hue (e.g. red) stays saturated and never
                washes out to pink the way a white soft-light blend would. */}
            <feBlend in="SourceGraphic" in2="diffClip" mode="multiply" result="shaded" />

            {/* Narrow inner top highlight — the puffy clay sheen, kept subtle. */}
            <feOffset in="SourceAlpha" dx="0" dy="5" result="hiOff" />
            <feComposite in="SourceAlpha" in2="hiOff" operator="out" result="hiEdge" />
            <feGaussianBlur in="hiEdge" stdDeviation="2" result="hiBlur" />
            <feComposite in="hiBlur" in2="SourceAlpha" operator="in" result="hiClip" />
            <feFlood floodColor="#ffffff" floodOpacity="0.45" result="hiColor" />
            <feComposite in="hiColor" in2="hiClip" operator="in" result="highlight" />

            {/* Inner bottom shade — soft, same-family dark so it never looks dirty. */}
            <feOffset in="SourceAlpha" dx="0" dy="-5" result="shOff" />
            <feComposite in="SourceAlpha" in2="shOff" operator="out" result="shEdge" />
            <feGaussianBlur in="shEdge" stdDeviation="2.6" result="shBlur" />
            <feComposite in="shBlur" in2="SourceAlpha" operator="in" result="shClip" />
            <feFlood floodColor="#1f2a1c" floodOpacity="0.2" result="shColor" />
            <feComposite in="shColor" in2="shClip" operator="in" result="shade" />

            <feMerge>
              <feMergeNode in="shaded" />
              <feMergeNode in="shade" />
              <feMergeNode in="highlight" />
            </feMerge>
          </filter>
        </defs>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(150,160,145,0.22)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          filter={`url(#ring-emboss-${verdict})`}
          style={{ transition: "stroke-dashoffset 1s ease" }}
        />
      </svg>
      <div className="risk-gauge-center">
        <span className="risk-gauge-score" style={{ color }}>
          {clamped}
        </span>
        <span className="risk-gauge-max muted">/ 100</span>
        <span className="risk-gauge-label" style={{ color }}>
          {VERDICT_LABEL[verdict]}
        </span>
      </div>
    </div>
  );
}

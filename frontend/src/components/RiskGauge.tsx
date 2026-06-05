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
    <div className="risk-gauge neu-inset" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(150,160,145,0.3)"
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

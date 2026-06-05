import type { DimensionResult } from "../types";
import { scoreToVerdict } from "../types";

interface ScoreCardProps {
  icon: string;
  title: string;
  /** Optional weight shown as a small chip, e.g. "40%". */
  weight?: string;
  result: DimensionResult;
}

const BAR_COLOR = {
  safe: "var(--safe)",
  caution: "var(--caution)",
  danger: "var(--danger)",
} as const;

/** A glass card showing one analysis dimension's score, bar, flags and detail. */
export function ScoreCard({ icon, title, weight, result }: ScoreCardProps) {
  const verdict = scoreToVerdict(result.score);
  const color = BAR_COLOR[verdict];

  return (
    <div className="score-card glass">
      <div className="score-card-head">
        <span className="score-card-icon" aria-hidden="true">
          {icon}
        </span>
        <div className="score-card-titles">
          <h3 className="score-card-title">{title}</h3>
          {weight && <span className="score-card-weight">{weight}</span>}
        </div>
        <span className="score-card-value" style={{ color }}>
          {result.score}
        </span>
      </div>

      <div className="score-bar-track">
        <div
          className="score-bar-fill"
          style={{ width: `${Math.max(2, result.score)}%`, background: color }}
        />
      </div>

      {result.flags.length > 0 && (
        <div className="score-flags">
          {result.flags.map((flag) => (
            <span key={flag} className="score-flag" style={{ color }}>
              {flag.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      )}

      <p className="score-detail muted">{result.detail}</p>
    </div>
  );
}

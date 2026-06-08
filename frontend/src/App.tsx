import { useState } from "react";
import { PitchScene } from "./components/PitchScene";
import { UrlInputScreen } from "./components/UrlInputScreen";
import { ReportScreen } from "./components/ReportScreen";
import { CameraStage } from "./flow/CameraStage";
import { useFlow } from "./flow/useFlow";
import { auditUrl } from "./api";
import type { TicketReport } from "./types";
import "./flow/flow.css";

export default function App() {
  const flow = useFlow();
  const [report, setReport] = useState<TicketReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAudit = async (url: string) => {
    setError(null);
    setLoading(true);
    // Start the cinematic flow immediately; fetch the report in the background
    // so its data is ready by the time the camera reaches the report scene.
    flow.start(url);
    try {
      const result = await auditUrl(url);
      setReport(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Audit failed. Try again.");
      flow.reset();
    } finally {
      setLoading(false);
    }
  };

  const handleBack = () => {
    setReport(null);
    flow.reset();
  };

  const aboveBalls = flow.phase === "report";

  return (
    <>
      <PitchScene />
      <main className={`app-shell${aboveBalls ? " app-shell--above-balls" : ""}`}>
        <CameraStage
          flow={flow}
          input={
            <UrlInputScreen
              onAudit={handleAudit}
              loading={loading}
              error={error}
            />
          }
          report={
            report ? (
              <ReportScreen report={report} onBack={handleBack} />
            ) : (
              <div className="flow-placeholder">
                <span className="flow-placeholder-dot" aria-hidden="true" />
                <span className="flow-placeholder-label">Finalising…</span>
              </div>
            )
          }
        />
      </main>
    </>
  );
}

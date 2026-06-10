import { useState } from "react";
import { PitchScene } from "./components/PitchScene";
import { UrlInputScreen } from "./components/UrlInputScreen";
import { ReportScreen } from "./components/ReportScreen";
import { CameraStage } from "./flow/CameraStage";
import { useFlow } from "./flow/useFlow";
import { auditUrl } from "./api";
import type { TicketReport } from "./types";
import type { ThreatScanCache } from "./components/ThreatIntelPanel";
import type { AgentState } from "./components/agent/useAgentStream";
import { usePriceStream } from "./components/price/usePriceStream";
import "./flow/flow.css";

export default function App() {
  const flow = useFlow();
  const [report, setReport] = useState<TicketReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [threatCache, setThreatCache] = useState<ThreatScanCache | null>(null);
  const [agentCache, setAgentCache] = useState<AgentState | null>(null);
  const [qty, setQty] = useState(2);

  // The price scrape (headed browser, ~minutes) is hosted here at the App level
  // so it survives the pipeline → report phase transition: it STARTS and shows
  // live in the pipeline's price unit, and the SAME state feeds the report's
  // result panel. Enabled once an audit begins.
  const price = usePriceStream(
    flow.url ?? "",
    qty,
    flow.started && !!flow.url,
  );

  const handleAudit = async (url: string, ticketQty: number) => {
    setError(null);
    setLoading(true);
    setQty(ticketQty);
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
    setThreatCache(null);
    setAgentCache(null);
    flow.reset();
  };

  // Keep the flow content above the falling balls for every phase except the
  // initial input screen (where the balls play in front as the hero effect).
  const aboveBalls = flow.phase !== "input";

  return (
    <>
      <PitchScene />
      <main className={`app-shell${aboveBalls ? " app-shell--above-balls" : ""}`}>
        <CameraStage
          flow={flow}
          onScanComplete={setThreatCache}
          onAgentComplete={setAgentCache}
          price={price}
          reportReady={report !== null}
          input={
            <UrlInputScreen
              onAudit={handleAudit}
              loading={loading}
              error={error}
            />
          }
          report={
            report ? (
              <ReportScreen
                report={report}
                onBack={handleBack}
                threatCache={threatCache ?? undefined}
                agentCache={agentCache ?? undefined}
                price={price}
              />
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

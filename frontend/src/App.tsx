import { useEffect, useState } from "react";
import { PitchScene } from "./components/PitchScene";
import { UrlInputScreen } from "./components/UrlInputScreen";
import { ReportScreen } from "./components/ReportScreen";
import { CameraStage } from "./flow/CameraStage";
import { useFlow } from "./flow/useFlow";
import { buildReportFromCache } from "./api";
import type { TicketReport } from "./types";
import type { ThreatScanCache } from "./components/ThreatIntelPanel";
import type { AgentState } from "./components/agent/useAgentStream";
import { usePriceStream } from "./components/price/usePriceStream";
import "./flow/flow.css";

export default function App() {
  const flow = useFlow();
  const [report, setReport] = useState<TicketReport | null>(null);
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

  const handleAudit = (url: string, ticketQty: number) => {
    setError(null);
    setQty(ticketQty);
    setReport(null);
    setThreatCache(null);
    setAgentCache(null);
    // Start the cinematic flow. Every backend source runs ONCE during the
    // pipeline phase (threat scan + opinion agent + price); the report is then
    // assembled from those caches — it never calls the backend itself.
    flow.start(url);
  };

  // Assemble the report from pipeline caches — no backend call. Ready once the
  // threat scan has finished and, in the grey zone, the opinion agent too.
  useEffect(() => {
    if (report || !flow.url || !threatCache) return;
    if (threatCache.greyZone && !agentCache) return;
    setReport(buildReportFromCache(flow.url, threatCache, agentCache));
  }, [report, flow.url, threatCache, agentCache]);

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
              loading={false}
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

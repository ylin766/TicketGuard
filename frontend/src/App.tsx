import { useEffect, useState } from "react";
import { PitchScene } from "./components/PitchScene";
import { UrlInputScreen } from "./components/UrlInputScreen";
import { ReportScreen } from "./components/ReportScreen";
import { CameraStage } from "./flow/CameraStage";
import { useFlow } from "./flow/useFlow";
import { buildReportFromCache } from "./api";
import type { TicketReport } from "./types";
import type { ThreatScanCache } from "./components/ThreatIntelPanel";
import { useAgentStream } from "./components/agent/useAgentStream";
import { useBrowserCheckStream } from "./components/agent/useBrowserCheckStream";
import { usePriceStream } from "./components/price/usePriceStream";
import "./flow/flow.css";

export default function App() {
  const flow = useFlow();
  const [report, setReport] = useState<TicketReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [threatCache, setThreatCache] = useState<ThreatScanCache | null>(null);
  const [qty, setQty] = useState(2);

  // ALL live streams are owned here, at the App top level, so each one is a
  // SINGLE instance that survives the pipeline → report phase transition. The
  // runtime phase RUNS them (their live frames feed the pipeline units); the
  // report phase only DISPLAYS the very same state. Because the hooks never
  // unmount and their deps (url / enabled) don't change across the transition,
  // nothing re-fires on the report page — no "completion guard" patch needed.
  //
  // Price runs for every audit; the grey-zone agent + Layer-2 browser probe run
  // only when the threat scan lands in the grey zone (escalation), gated on the
  // scan's authoritative decision carried in the cache.
  const greyZone = threatCache?.greyZone === true;
  const price = usePriceStream(
    flow.url ?? "",
    qty,
    flow.started && !!flow.url,
  );
  const agent = useAgentStream(flow.url ?? "", flow.started && greyZone);
  const browser = useBrowserCheckStream(flow.url ?? "", flow.started && greyZone);

  const handleAudit = (url: string, ticketQty: number) => {
    setError(null);
    setQty(ticketQty);
    setReport(null);
    setThreatCache(null);
    // Start the cinematic flow. Every backend source runs ONCE during the
    // pipeline phase (threat scan + opinion agent + price); the report is then
    // assembled from those caches — it never calls the backend itself.
    flow.start(url);
  };

  // Assemble the report from the live stream state — no backend call. Ready once
  // the threat scan has finished and, in the grey zone, the opinion agent too.
  useEffect(() => {
    if (report || !flow.url || !threatCache) return;
    if (greyZone && agent.status !== "done" && agent.status !== "error") return;
    setReport(buildReportFromCache(flow.url, threatCache, greyZone ? agent : null));
  }, [report, flow.url, threatCache, greyZone, agent]);

  const handleBack = () => {
    setReport(null);
    setThreatCache(null);
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
          agentState={agent}
          browserState={browser}
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
                agentCache={greyZone ? agent : undefined}
                browserCache={greyZone ? browser : undefined}
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

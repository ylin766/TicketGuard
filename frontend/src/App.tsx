import { useState } from "react";
import { AnimatePresence } from "framer-motion";
import { PitchScene } from "./components/PitchScene";
import { UrlInputScreen } from "./components/UrlInputScreen";
import { ReportScreen } from "./components/ReportScreen";
import { auditUrl } from "./api";
import type { TicketReport } from "./types";

type View = "input" | "report";

export default function App() {
  const [view, setView] = useState<View>("input");
  const [report, setReport] = useState<TicketReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAudit = async (url: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await auditUrl(url);
      setReport(result);
      setView("report");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Audit failed. Try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleBack = () => {
    setView("input");
  };

  return (
    <>
      <PitchScene />
      <main className="app-shell">
        <AnimatePresence mode="wait">
          {view === "input" || !report ? (
            <UrlInputScreen
              key="input"
              onAudit={handleAudit}
              loading={loading}
              error={error}
            />
          ) : (
            <ReportScreen key="report" report={report} onBack={handleBack} />
          )}
        </AnimatePresence>
      </main>
    </>
  );
}

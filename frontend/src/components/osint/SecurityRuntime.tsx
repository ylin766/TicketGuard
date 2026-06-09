import { useState } from "react";
import { ThreatIntelPanel } from "../ThreatIntelPanel";
import { OsintPanel } from "./OsintPanel";
import { useOsintStream } from "./useOsintStream";

/**
 * The security unit's runtime body. It runs the two security investigations in
 * sequence so the user can watch each:
 *
 *   1. Threat Intelligence — the 13-source deterministic scan (runtime variant).
 *   2. Public Opinion Investigation — once the scan settles, the OSINT agent
 *      streams its multi-step social/web investigation trace.
 *
 * The flow only advances to the report once BOTH have finished (the agent is
 * the slower, LLM-driven step), so `onDone` fires when the OSINT stream ends.
 */
export function SecurityRuntime({
  url,
  onDone,
}: {
  url: string;
  onDone: () => void;
}) {
  const [scanDone, setScanDone] = useState(false);
  const osint = useOsintStream(url, scanDone, onDone);

  return (
    <div className="security-runtime">
      <ThreatIntelPanel
        url={url}
        variant="runtime"
        onDone={() => setScanDone(true)}
      />
      {scanDone && <OsintPanel state={osint} />}
    </div>
  );
}

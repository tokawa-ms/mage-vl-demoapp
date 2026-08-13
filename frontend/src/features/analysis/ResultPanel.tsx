import { Check, Clipboard, Clock3, Download, MemoryStick, Settings2, TriangleAlert } from "lucide-react";
import { useState } from "react";
import type { AnalysisJob } from "../../types/api";
import { StreamingTimeline } from "./StreamingTimeline";

export function ResultPanel({ job }: { job: AnalysisJob }) {
  const [copied, setCopied] = useState(false);
  const result = job.result!;
  const answer = typeof result.answer === "string" ? result.answer : "";
  const timeline = Array.isArray(result.timeline) ? result.timeline : [];

  const copy = async () => {
    await navigator.clipboard.writeText(answer);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };
  const download = () => {
    const blob = new Blob([JSON.stringify({ id: job.id, status: job.status, result }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `mage-vl-${job.id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="result-panel">
      <div className="result-header">
        <div><span className="eyebrow">Model response</span><h2>Result</h2></div>
        <div className="result-actions">
          <button className="icon-button" type="button" onClick={copy} aria-label="Copy answer">{copied ? <Check size={17} /> : <Clipboard size={17} />}</button>
          <button className="icon-button" type="button" onClick={download} aria-label="Download result JSON"><Download size={17} /></button>
        </div>
      </div>
      {answer && <div className="answer"><span className="answer-rule" /><p>{answer}</p></div>}
      <div className="telemetry-grid">
        <Telemetry icon={<Clock3 size={15} />} label="Timing" value={formatRecord(result.timings)} />
        <Telemetry icon={<Settings2 size={15} />} label="Settings" value={formatRecord(result.settings)} />
        <Telemetry icon={<MemoryStick size={15} />} label="VRAM" value={formatVram(result.vram)} />
      </div>
      {result.warnings?.length ? <div className="warnings"><TriangleAlert size={17} /><div><strong>Run warnings</strong>{result.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div></div> : null}
      {timeline.length > 0 && <StreamingTimeline events={timeline} />}
    </section>
  );
}

function Telemetry({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return <div className="telemetry-card"><span>{icon}{label}</span><strong>{value || "—"}</strong></div>;
}

function formatRecord(value: unknown) {
  if (!value || typeof value !== "object") return "";
  return Object.entries(value as Record<string, unknown>).map(([key, item]) => `${key.replaceAll("_", " ")}: ${String(item)}`).join(" · ");
}

function formatVram(value: unknown) {
  if (typeof value === "string" || typeof value === "number") return String(value);
  return formatRecord(value);
}

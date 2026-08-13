import { Check, CircleStop, LoaderCircle, Radio, TriangleAlert } from "lucide-react";
import type { AnalysisJob } from "../../types/api";

const stages = [
  { id: "queued", label: "Queue" },
  { id: "running", label: "Model" },
  { id: "preprocessing", label: "Prepare" },
  { id: "generating", label: "Generate" },
  { id: "completed", label: "Complete" },
] as const;

export function JobProgress({ job, connected, onCancel }: { job: AnalysisJob; connected: boolean; onCancel: () => void }) {
  const index = stages.findIndex((stage) => stage.id === job.status);
  const isActive = !["completed", "failed", "cancelled"].includes(job.status);
  return (
    <section className="progress-panel" aria-live="polite">
      <div className="progress-topline">
        <div>
          <span className="eyebrow">{connected && <Radio size={12} />} {connected ? "Live event stream" : "Job state"}</span>
          <h2>{labelFor(job.status)}</h2>
        </div>
        {isActive && <button className="secondary-button danger" type="button" onClick={onCancel}><CircleStop size={16} /> Cancel</button>}
      </div>
      <div className="stage-track">
        {stages.map((stage, stageIndex) => (
          <div className={`stage ${stageIndex <= index ? "passed" : ""} ${stage.id === job.status ? "current" : ""}`} key={stage.id}>
            <span>{stageIndex < index || job.status === "completed" ? <Check size={12} /> : stage.id === job.status ? <LoaderCircle size={12} /> : stageIndex + 1}</span>
            <small>{stage.label}</small>
          </div>
        ))}
      </div>
      <div className="progress-meter" role="progressbar" aria-valuenow={job.progress} aria-valuemin={0} aria-valuemax={100}>
        <span style={{ width: `${job.progress}%` }} />
      </div>
      <div className="progress-caption">
        <span>{job.message || (job.queuePosition ? `Waiting in queue · position ${job.queuePosition}` : "Processing request")}</span>
        <strong>{Math.round(job.progress)}%</strong>
      </div>
      {job.status === "failed" && <div className="inline-error"><TriangleAlert size={16} /> {job.error || "Analysis failed"}</div>}
    </section>
  );
}

function labelFor(status: AnalysisJob["status"]) {
  return ({
    queued: "Queued for inference",
    running: "Running analysis",
    loading_model: "Loading model",
    preprocessing: "Preparing visual tokens",
    generating: "Generating response",
    completed: "Analysis complete",
    failed: "Analysis failed",
    cancelled: "Analysis cancelled",
  })[status] || status;
}

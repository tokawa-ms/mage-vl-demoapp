import { useEffect, useMemo, useState } from "react";
import { Activity, Cpu, Gauge, Sparkles } from "lucide-react";
import { AnalysisForm } from "../features/analysis/AnalysisForm";
import { JobProgress } from "../features/analysis/JobProgress";
import { ResultPanel } from "../features/analysis/ResultPanel";
import { SystemCard } from "../features/system/SystemCard";
import { getCapabilities, getModelStatus } from "../lib/api";
import { useAnalysisJob } from "../lib/useAnalysisJob";
import type { Capabilities, ModelStatus } from "../types/api";

export function App() {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [systemError, setSystemError] = useState("");
  const job = useAnalysisJob();

  useEffect(() => {
    let active = true;
    Promise.all([getCapabilities(), getModelStatus()])
      .then(([nextCapabilities, nextStatus]) => {
        if (!active) return;
        setCapabilities(nextCapabilities);
        setModelStatus(nextStatus);
      })
      .catch((error: unknown) => {
        if (active) setSystemError(error instanceof Error ? error.message : "System status unavailable");
      });
    return () => {
      active = false;
    };
  }, []);

  const supportedCount = useMemo(
    () => Object.values(capabilities?.modes ?? {}).filter((mode) => mode.supported).length,
    [capabilities],
  );

  return (
    <div className="app-shell">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <header className="topbar">
        <a className="brand" href="/" aria-label="Mage VL Studio home">
          <span className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span>
            <strong>MAGE·VL</strong>
            <small>VIDEO INTELLIGENCE STUDIO</small>
          </span>
        </a>
        <div className="topbar-status">
          <span className={`status-dot ${systemError ? "is-error" : ""}`} />
          {systemError ? "System check failed" : capabilities ? "Workspace online" : "Connecting"}
        </div>
      </header>

      <main className="workspace">
        <section className="hero" aria-labelledby="page-title">
          <div>
            <span className="eyebrow"><Sparkles size={14} /> Multimodal inference console</span>
            <h1 id="page-title">Read every frame.<br /><em>Understand the whole story.</em></h1>
          </div>
          <p>Upload visual media, choose an analysis path, and watch the model reason in real time.</p>
        </section>

        <section className="system-grid" aria-label="System status">
          <SystemCard
            icon={<Activity size={18} />}
            label="Engine"
            value={modelStatus?.loaded ? "Ready" : modelStatus?.loading ? "Warming up" : "Standby"}
            detail={modelStatus?.model ?? capabilities?.model ?? "Vision-language model"}
            tone={modelStatus?.loaded ? "green" : "amber"}
          />
          <SystemCard
            icon={<Cpu size={18} />}
            label="Compute"
            value={capabilities?.gpu.available ? capabilities.gpu.name || "GPU" : "CPU"}
            detail={capabilities?.gpu.vramTotalGb ? `${capabilities.gpu.vramTotalGb} GB VRAM available` : "Hardware auto-detected"}
            tone={capabilities?.gpu.available ? "cyan" : "neutral"}
          />
          <SystemCard
            icon={<Gauge size={18} />}
            label="Capabilities"
            value={capabilities ? `${supportedCount} / 5 modes` : "Discovering"}
            detail={capabilities?.version ? `Runtime ${capabilities.version}` : "Checking codec support"}
            tone="violet"
          />
        </section>

        {systemError && <div className="notice error-notice" role="alert">{systemError}. Analysis controls remain available.</div>}

        <div className="studio-grid">
          <AnalysisForm
            capabilities={capabilities}
            disabled={job.isActive}
            onSubmit={job.start}
          />
          <aside className="output-column" aria-label="Analysis output">
            {job.job ? (
              <>
                <JobProgress job={job.job} connected={job.connected} onCancel={job.cancel} />
                {job.job.result && <ResultPanel job={job.job} />}
              </>
            ) : (
              <div className="empty-output">
                <div className="scan-visual" aria-hidden="true">
                  <span className="scan-line" />
                  <span className="scan-corner corner-a" />
                  <span className="scan-corner corner-b" />
                  <Sparkles size={28} />
                </div>
                <span className="eyebrow">Output monitor</span>
                <h2>Analysis will appear here</h2>
                <p>Configure a run on the left. Progress, reasoning, telemetry, and results stream into this panel.</p>
              </div>
            )}
            {job.error && <div className="notice error-notice" role="alert">{job.error}</div>}
          </aside>
        </div>
      </main>
      <footer>
        <span>MAGE·VL / LOCAL INFERENCE</span>
        <span>Media stays within your environment</span>
      </footer>
    </div>
  );
}

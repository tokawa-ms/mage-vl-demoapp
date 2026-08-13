import { useCallback, useEffect, useRef, useState } from "react";
import { apiBaseUrl, cancelAnalysis, getAnalysis, getAnalysisResult, mergeJob, submitAnalysis } from "./api";
import type { AnalysisJob, AnalysisSubmission } from "../types/api";

const terminal = new Set(["completed", "failed", "cancelled"]);

export function useAnalysisJob() {
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [error, setError] = useState("");
  const [connected, setConnected] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);
  const jobId = job?.id;

  useEffect(() => {
    if (!jobId) return;
    let active = true;
    let retryTimer: number | undefined;

    function openSource() {
      const source = new EventSource(`${apiBaseUrl}/api/analyses/${encodeURIComponent(jobId!)}/events`);
      sourceRef.current = source;
      source.onopen = () => {
        if (active) setConnected(true);
      };
      const handleEvent = async (event: MessageEvent, eventName = "status") => {
        try {
          const update = JSON.parse(event.data) as { status?: string; message?: string };
          if (eventName === "segment") {
            setJob((current) => current ? {
              ...current,
              result: {
                ...current.result,
                timeline: [...(current.result?.timeline ?? []), {
                  timestamp: Number((update as Record<string, unknown>).start_seconds ?? 0),
                  probability: Number((update as Record<string, unknown>).gate_probability ?? 0),
                  decision: String((update as Record<string, unknown>).decision ?? "silence"),
                  text: typeof (update as Record<string, unknown>).answer === "string" ? String((update as Record<string, unknown>).answer) : undefined,
                }],
              },
            } : null);
            return;
          }
          if (eventName === "warning") {
            setJob((current) => current ? {
              ...current,
              result: {
                ...current.result,
                warnings: [...(current.result?.warnings ?? []), update.message ?? "Inference warning"],
              },
            } : null);
            return;
          }
          setJob((current) => current ? mergeJob(current, update) : null);
          if (update.status === "completed") {
            const result = await getAnalysisResult(jobId!);
            if (active) setJob((current) => current ? { ...current, status: "completed", progress: 100, result } : null);
          }
          if (update.status && terminal.has(update.status)) {
            source.close();
            setConnected(false);
          }
        } catch {
          setError("Received an invalid progress event.");
        }
      };
      source.onmessage = (event) => void handleEvent(event);
      for (const eventName of ["status", "progress", "segment", "warning"]) {
        source.addEventListener(eventName, ((event: MessageEvent) => void handleEvent(event, eventName)) as EventListener);
      }
      source.onerror = async () => {
        source.close();
        setConnected(false);
        try {
          const recovered = await getAnalysis(jobId!);
          if (!active) return;
          if (recovered.status === "completed" && !recovered.result) {
            recovered.result = await getAnalysisResult(jobId!);
          }
          setJob(recovered);
          if (!terminal.has(recovered.status)) retryTimer = window.setTimeout(openSource, 1500);
        } catch (recoveryError) {
          if (active) setError(recoveryError instanceof Error ? recoveryError.message : "Unable to reconnect to analysis.");
        }
      };
    }

    openSource();
    return () => {
      active = false;
      sourceRef.current?.close();
      sourceRef.current = null;
      if (retryTimer) window.clearTimeout(retryTimer);
    };
  }, [jobId]);

  const start = useCallback(async (values: AnalysisSubmission) => {
    setError("");
    try {
      const created = await submitAnalysis(values);
      if (!created.id) throw new Error("Analysis response did not include a job ID.");
      setJob(created);
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "Unable to start analysis.");
    }
  }, []);

  const cancel = useCallback(async () => {
    if (!job) return;
    try {
      const updated = await cancelAnalysis(job.id);
      setJob((current) => current ? mergeJob(current, updated) : updated);
    } catch (cancelError) {
      setError(cancelError instanceof Error ? cancelError.message : "Unable to cancel analysis.");
    }
  }, [job]);

  return { job, error, connected, start, cancel, isActive: Boolean(job && !terminal.has(job.status)) };
}

import { analysisModes, type AnalysisJob, type AnalysisMode, type AnalysisSubmission, type Capabilities, type ModelStatus } from "../types/api";

export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, init);
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" ? value as Record<string, unknown> : {};

export async function getCapabilities(): Promise<Capabilities> {
  const raw = asRecord(await request<unknown>("/api/capabilities"));
  const rawModes = asRecord(raw.modes);
  const supported = Array.isArray(raw.supported_modes) ? raw.supported_modes : null;
  const modes = Object.fromEntries(analysisModes.map((mode) => {
    const entry = rawModes[mode];
    const info = asRecord(entry);
    const explicit = typeof entry === "boolean" ? entry : info.supported;
    const isSupported = typeof explicit === "boolean" ? explicit : supported ? supported.includes(mode) : true;
    return [mode, {
      supported: isSupported,
      reason: typeof info.reason === "string" ? info.reason : typeof info.message === "string" ? info.message : undefined,
    }];
  })) as Record<AnalysisMode, { supported: boolean; reason?: string }>;
  const gpu = asRecord(raw.gpu);
  const cuda = asRecord(raw.cuda);
  const devices = Array.isArray(cuda.devices) ? cuda.devices : [];
  const firstDevice = asRecord(devices[0]);
  const totalBytes = Number(firstDevice.total_memory_bytes);
  return {
    modes,
    gpu: {
      available: Boolean(gpu.available ?? cuda.available ?? raw.gpu_available),
      name: String(gpu.name ?? firstDevice.name ?? raw.gpu_name ?? "").trim() || undefined,
      vramTotalGb: Number(gpu.vram_total_gb ?? gpu.vram_gb ?? raw.vram_total_gb) || (totalBytes ? Math.round(totalBytes / 2 ** 30 * 10) / 10 : undefined),
    },
    model: typeof raw.model === "string" ? raw.model : undefined,
    version: typeof raw.version === "string" ? raw.version : undefined,
  };
}

export async function getModelStatus(): Promise<ModelStatus> {
  const raw = asRecord(await request<unknown>("/api/model/status"));
  const status = String(raw.status ?? raw.state ?? "");
  return {
    loaded: Boolean(raw.loaded ?? (status === "ready" || status === "loaded")),
    loading: Boolean(raw.loading ?? status === "loading"),
    model: typeof raw.model === "string" ? raw.model : typeof raw.model_name === "string" ? raw.model_name : typeof raw.model_id === "string" ? raw.model_id : undefined,
    progress: Number(raw.progress) || undefined,
    message: typeof raw.message === "string" ? raw.message : undefined,
  };
}

export function submitAnalysis(values: AnalysisSubmission): Promise<AnalysisJob> {
  const body = new FormData();
  body.append("media", values.file);
  body.append("mode", values.mode);
  body.append("question", values.question);
  body.append("num_frames", String(values.frames));
  body.append("max_pixels", String(values.maxPixels));
  body.append("max_new_tokens", String(values.maxTokens));
  body.append("segment_sec", String(values.segmentSec));
  body.append("gate_threshold", String(values.gateThreshold));
  return request<unknown>("/api/analyses", { method: "POST", body }).then(normalizeJob);
}

export function getAnalysis(id: string): Promise<AnalysisJob> {
  return request<unknown>(`/api/analyses/${encodeURIComponent(id)}`).then(normalizeJob);
}

export function cancelAnalysis(id: string): Promise<AnalysisJob> {
  return request<unknown>(
    `/api/analyses/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  ).then(normalizeJob);
}

export function normalizeJob(value: unknown, fallbackId = ""): AnalysisJob {
  const raw = asRecord(value);
  const result = normalizeResult(raw.result);
  const status = String(raw.status ?? raw.state ?? "queued") as AnalysisJob["status"];
  const rawProgress = Number(raw.progress ?? raw.percent ?? (status === "completed" ? 1 : 0));
  return {
    id: String(raw.id ?? raw.job_id ?? fallbackId),
    status,
    progress: Math.max(0, Math.min(100, rawProgress <= 1 ? rawProgress * 100 : rawProgress)),
    message: typeof raw.message === "string" ? raw.message : undefined,
    queuePosition: Number(raw.queue_position ?? raw.queuePosition) || undefined,
    result: result ?? undefined,
    error: typeof raw.error === "string" ? raw.error : undefined,
    mode: analysisModes.includes(raw.mode as AnalysisMode) ? raw.mode as AnalysisMode : undefined,
  };
}

export async function getAnalysisResult(id: string): Promise<Record<string, unknown>> {
  return normalizeResult(await request<unknown>(`/api/analyses/${encodeURIComponent(id)}/result`)) ?? {};
}

function normalizeResult(value: unknown): Record<string, unknown> | null {
  const raw = asRecord(value);
  if (!Object.keys(raw).length) return null;
  const segments = Array.isArray(raw.segments) ? raw.segments.map((item) => {
    const segment = asRecord(item);
    return {
      timestamp: Number(segment.start_seconds ?? segment.timestamp ?? 0),
      probability: Number(segment.gate_probability ?? segment.probability ?? 0),
      decision: String(segment.decision ?? "silence"),
      text: typeof segment.answer === "string" ? segment.answer : typeof segment.text === "string" ? segment.text : undefined,
    };
  }) : [];
  return {
    ...raw,
    timings: asRecord(raw.timings ?? raw.metrics),
    vram: raw.vram ?? asRecord(raw.metrics).gpu_memory,
    timeline: Array.isArray(raw.timeline) ? raw.timeline : segments,
  };
}

export function mergeJob(current: AnalysisJob, update: unknown): AnalysisJob {
  const raw = asRecord(update);
  const normalized = normalizeJob({ ...current, ...raw, id: raw.id ?? current.id }, current.id);
  return {
    ...current,
    ...normalized,
    result: normalized.result ?? current.result,
  };
}

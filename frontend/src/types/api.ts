export const analysisModes = ["image", "video_frames", "traditional_codec", "neural_codec", "streaming"] as const;
export type AnalysisMode = (typeof analysisModes)[number];

export interface ModeCapability {
  supported: boolean;
  reason?: string;
}

export interface Capabilities {
  modes: Record<AnalysisMode, ModeCapability>;
  gpu: {
    available: boolean;
    name?: string;
    vramTotalGb?: number;
  };
  model?: string;
  version?: string;
}

export interface ModelStatus {
  loaded: boolean;
  loading: boolean;
  model?: string;
  progress?: number;
  message?: string;
}

export type JobStatus = "queued" | "running" | "loading_model" | "preprocessing" | "generating" | "completed" | "failed" | "cancelled";

export interface StreamEvent {
  timestamp: number | string;
  probability: number;
  decision: string;
  text?: string;
}

export interface AnalysisResult {
  answer?: string;
  timings?: Record<string, number | string>;
  settings?: Record<string, unknown>;
  vram?: Record<string, number | string> | number | string;
  warnings?: string[];
  timeline?: StreamEvent[];
  [key: string]: unknown;
}

export interface AnalysisJob {
  id: string;
  status: JobStatus;
  progress: number;
  message?: string;
  queuePosition?: number;
  result?: AnalysisResult;
  error?: string;
  mode?: AnalysisMode;
}

export interface AnalysisSubmission {
  file: File;
  mode: AnalysisMode;
  question: string;
  frames: number;
  maxPixels: number;
  maxTokens: number;
  segmentSec: number;
  gateThreshold: number;
}

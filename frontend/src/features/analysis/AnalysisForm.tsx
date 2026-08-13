import { useState, type FormEvent } from "react";
import { ArrowRight, SlidersHorizontal } from "lucide-react";
import type { AnalysisMode, AnalysisSubmission, Capabilities } from "../../types/api";
import { FileUploader } from "./FileUploader";
import { ModeSelector } from "./ModeSelector";

const MIN_MAX_PIXELS = 65536;
const MAX_MAX_PIXELS = 300000;
const MAX_PIXELS_STEP = 16384;

function normalizeMaxPixels(value: number): number {
  if (!Number.isFinite(value)) return 98304;
  const clamped = Math.min(MAX_MAX_PIXELS, Math.max(MIN_MAX_PIXELS, value));
  return MIN_MAX_PIXELS
    + Math.floor((clamped - MIN_MAX_PIXELS) / MAX_PIXELS_STEP) * MAX_PIXELS_STEP;
}

const defaults = { frames: 16, maxPixels: 98304, maxTokens: 128, segmentSec: 8, gateThreshold: 0.5 };

export function AnalysisForm({ capabilities, disabled, onSubmit }: {
  capabilities: Capabilities | null;
  disabled?: boolean;
  onSubmit: (values: AnalysisSubmission) => void | Promise<void>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<AnalysisMode>("image");
  const [question, setQuestion] = useState("Describe what is happening in this media.");
  const [settings, setSettings] = useState(defaults);
  const [error, setError] = useState("");
  const fallbackMode = capabilities
    ? Object.entries(capabilities.modes).find(([, value]) => value.supported)?.[0] as AnalysisMode | undefined
    : undefined;
  const selectedMode = capabilities?.modes[mode].supported === false && fallbackMode ? fallbackMode : mode;

  const setNumber = (key: keyof typeof defaults, value: string) =>
    setSettings((current) => ({ ...current, [key]: Number(value) }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!file) {
      setError("Choose an image or video to begin.");
      return;
    }
    if (selectedMode === "image" && file.type.startsWith("video/")) {
      setError("Image mode requires an image file. Choose a video analysis path for video.");
      return;
    }
    setError("");
    const normalizedSettings = {
      ...settings,
      maxPixels: normalizeMaxPixels(settings.maxPixels),
    };
    setSettings(normalizedSettings);
    void onSubmit({ file, mode: selectedMode, question, ...normalizedSettings });
  };

  return (
    <form className="control-panel" onSubmit={submit}>
      <div className="panel-heading">
        <div><span className="step-number">01</span><div><span>Input source</span><h2>Configure analysis</h2></div></div>
        <SlidersHorizontal size={19} />
      </div>
      <FileUploader file={file} onChange={setFile} disabled={disabled} />
      <ModeSelector value={selectedMode} onChange={setMode} capabilities={capabilities} disabled={disabled} />

      <div className="field-group">
        <label htmlFor="question">Question / instruction</label>
        <textarea id="question" value={question} disabled={disabled} onChange={(event) => setQuestion(event.target.value)} rows={3} maxLength={2000} />
        <span className="character-count">{question.length} / 2000</span>
      </div>

      <div className="settings-grid">
        {selectedMode !== "image" && (
          <NumberField id="frames" label="Sample frames" value={settings.frames} min={1} max={64} onChange={(v) => setNumber("frames", v)} disabled={disabled} />
        )}
        <NumberField
          id="max-pixels"
          label="Max pixels"
          value={settings.maxPixels}
          min={MIN_MAX_PIXELS}
          max={MAX_MAX_PIXELS}
          step={1}
          onChange={(v) => setNumber("maxPixels", v)}
          onBlur={() => setSettings((current) => ({
            ...current,
            maxPixels: normalizeMaxPixels(current.maxPixels),
          }))}
          disabled={disabled}
        />
        <NumberField id="max-tokens" label="Max tokens" value={settings.maxTokens} min={32} max={512} step={32} onChange={(v) => setNumber("maxTokens", v)} disabled={disabled} />
        {selectedMode === "streaming" && (
          <NumberField id="segment-sec" label="Segment seconds" value={settings.segmentSec} min={0.25} max={30} step={0.25} onChange={(v) => setNumber("segmentSec", v)} disabled={disabled} />
        )}
        {selectedMode === "streaming" && (
          <div className="field-group range-field">
            <div><label htmlFor="gate-threshold">Gate threshold</label><output htmlFor="gate-threshold">{settings.gateThreshold.toFixed(2)}</output></div>
            <input id="gate-threshold" type="range" min="0" max="1" step="0.05" value={settings.gateThreshold} disabled={disabled} onChange={(e) => setNumber("gateThreshold", e.target.value)} />
          </div>
        )}
      </div>
      {error && <div className="inline-error" role="alert">{error}</div>}
      <button className="primary-button" type="submit" disabled={disabled}>
        <span>{disabled ? "Analysis in progress" : "Run analysis"}</span><ArrowRight size={18} />
      </button>
    </form>
  );
}

function NumberField({ id, label, value, onChange, ...props }: {
  id: string; label: string; value: number; onChange: (value: string) => void;
  min: number; max: number; step?: number; disabled?: boolean; onBlur?: () => void;
}) {
  return <div className="field-group compact-field"><label htmlFor={id}>{label}</label><input id={id} type="number" value={value} onChange={(e) => onChange(e.target.value)} {...props} /></div>;
}

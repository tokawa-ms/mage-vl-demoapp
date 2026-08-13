import { Boxes, Clapperboard, Image, Radio, Waves } from "lucide-react";
import type { AnalysisMode, Capabilities } from "../../types/api";

const modes: Array<{ id: AnalysisMode; title: string; short: string; icon: typeof Image }> = [
  { id: "image", title: "Image", short: "Single frame", icon: Image },
  { id: "video_frames", title: "Frames", short: "Sampled video", icon: Clapperboard },
  { id: "traditional_codec", title: "Codec", short: "Traditional", icon: Boxes },
  { id: "neural_codec", title: "Neural", short: "Latent codec", icon: Waves },
  { id: "streaming", title: "Stream", short: "Timeline gate", icon: Radio },
];

export function ModeSelector({ value, onChange, capabilities, disabled }: {
  value: AnalysisMode;
  onChange: (mode: AnalysisMode) => void;
  capabilities: Capabilities | null;
  disabled?: boolean;
}) {
  return (
    <fieldset className="field-group mode-fieldset">
      <legend>Analysis path</legend>
      <div className="mode-grid">
        {modes.map(({ id, title, short, icon: Icon }) => {
          const capability = capabilities?.modes[id];
          const unsupported = capability?.supported === false;
          return (
            <label className={`mode-card ${value === id ? "selected" : ""} ${unsupported ? "unsupported" : ""}`} key={id}>
              <input
                type="radio"
                name="mode"
                value={id}
                checked={value === id}
                disabled={disabled || unsupported}
                onChange={() => onChange(id)}
              />
              <Icon size={19} />
              <strong>{title}</strong>
              <small>{unsupported ? "Unavailable" : short}</small>
              {unsupported && <span className="mode-reason" role="note">{capability.reason || "Not supported by this runtime"}</span>}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

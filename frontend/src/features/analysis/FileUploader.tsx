import { useCallback, useRef, useState } from "react";
import { FileImage, FileVideo, UploadCloud, X } from "lucide-react";

export function FileUploader({ file, onChange, disabled }: {
  file: File | null;
  onChange: (file: File | null) => void;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const accept = (candidate?: File) => {
    if (candidate?.type.startsWith("image/") || candidate?.type.startsWith("video/")) onChange(candidate);
  };

  if (file) {
    return (
      <MediaPreview
        key={`${file.name}:${file.size}:${file.lastModified}`}
        file={file}
        disabled={disabled}
        onRemove={() => onChange(null)}
      />
    );
  }

  return (
    <div
      className={`dropzone ${dragging ? "dragging" : ""}`}
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label="Upload image or video"
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(event) => {
        if (!disabled && (event.key === "Enter" || event.key === " ")) inputRef.current?.click();
      }}
      onDragOver={(event) => { event.preventDefault(); if (!disabled) setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        if (!disabled) accept(event.dataTransfer.files[0]);
      }}
    >
      <input ref={inputRef} type="file" accept="image/*,video/*" hidden disabled={disabled} onChange={(event) => accept(event.target.files?.[0])} />
      <span className="upload-icon"><UploadCloud size={26} /></span>
      <strong>Drop visual media here</strong>
      <span>or click to browse · images and video</span>
    </div>
  );
}

function MediaPreview({ file, disabled, onRemove }: { file: File; disabled?: boolean; onRemove: () => void }) {
  const [duration, setDuration] = useState<number>();
  const [previewError, setPreviewError] = useState("");
  const attachPreview = useCallback((element: HTMLVideoElement | HTMLImageElement | null) => {
    if (!element) return;
    const url = URL.createObjectURL(file);
    element.src = url;
    return () => {
      element.removeAttribute("src");
      URL.revokeObjectURL(url);
    };
  }, [file]);
  const isVideo = file.type.startsWith("video/");
  return (
    <div className="media-preview">
      <div className="media-surface">
        {isVideo ? (
          <video
            ref={attachPreview}
            controls
            playsInline
            preload="metadata"
            aria-label="Video preview"
            onLoadedMetadata={(event) => {
              const video = event.currentTarget;
              setDuration(video.duration);
              if (Number.isFinite(video.duration) && video.duration > 0) {
                video.currentTime = Math.min(0.1, video.duration / 100);
              }
            }}
            onError={() => setPreviewError(
              "This browser cannot preview the video's codec. Mage-VL can still analyze it.",
            )}
          />
        ) : <img ref={attachPreview} alt="Upload preview" />}
        {previewError && <div className="preview-error" role="status">{previewError}</div>}
      </div>
      <button className="icon-button remove-media" type="button" onClick={onRemove} disabled={disabled} aria-label="Remove media">
        <X size={17} />
      </button>
      <div className="media-meta">
        {isVideo ? <FileVideo size={16} /> : <FileImage size={16} />}
        <div><strong>{file.name}</strong><span>{formatBytes(file.size)}{duration ? ` · ${formatTime(duration)}` : ""} · {file.type.split("/")[1]?.toUpperCase()}</span></div>
      </div>
    </div>
  );
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTime(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${Math.floor(seconds % 60).toString().padStart(2, "0")}`;
}

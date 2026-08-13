from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnalysisMode(StrEnum):
    IMAGE = "image"
    VIDEO_FRAMES = "video_frames"
    TRADITIONAL_CODEC = "traditional_codec"
    NEURAL_CODEC = "neural_codec"
    STREAMING = "streaming"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisSettings(BaseModel):
    mode: AnalysisMode
    question: str = Field(min_length=1, max_length=8_000)
    num_frames: int = Field(32, ge=1)
    max_pixels: int = Field(150_000, ge=256)
    max_new_tokens: int = Field(256, ge=1)
    segment_sec: float = Field(8.0, gt=0)
    gate_threshold: float = Field(0.5, ge=0, le=1)


class MediaMetadata(BaseModel):
    media_type: str
    filename: str
    content_type: str | None = None
    size_bytes: int
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    fps: float | None = None
    frame_count: int | None = None
    codec: str | None = None


class AnalysisResult(BaseModel):
    analysis_id: str
    answer: str
    segments: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}
    warnings: list[str] = []
    settings: AnalysisSettings
    media: MediaMetadata


class AnalysisJob(BaseModel):
    id: str
    status: JobStatus
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress: float = Field(0, ge=0, le=1)
    message: str = ""
    error: str | None = None
    settings: AnalysisSettings
    media: MediaMetadata
    media_path: str
    result_path: str
    cancel_requested: bool = False
    retry_count: int = 0


class AnalysisCreated(BaseModel):
    id: str
    status: JobStatus


class ModelStatus(BaseModel):
    state: str
    model_id: str
    quantization: str
    loaded: bool
    device: str | None = None
    error: str | None = None

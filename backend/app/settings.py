from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

OFFICIAL_MODEL_ID = "microsoft/Mage-VL"
AUDITED_MODEL_REVISION = "d88b153285f1633a61b2f693c59c8576693af185"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MAGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    model_id: Literal["microsoft/Mage-VL"] | Path = OFFICIAL_MODEL_ID
    model_revision: Literal[
        "d88b153285f1633a61b2f693c59c8576693af185"
    ] = AUDITED_MODEL_REVISION
    quantization: Literal["4bit", "none"] = "4bit"
    preload_model: bool = False
    max_upload_mb: int = Field(1024, ge=1)
    max_video_seconds: float = Field(600, gt=0)
    max_frames: int = Field(64, ge=1)
    max_pixels: int = Field(300_000, ge=16 * 16)
    max_new_tokens: int = Field(512, ge=1)
    max_streaming_segments: int = Field(12, ge=1)
    job_retention_hours: float = Field(24, gt=0)
    upload_dir: Path = Path("data/uploads")
    result_dir: Path = Path("data/results")
    work_dir: Path = Path("data/work")
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    subprocess_timeout_seconds: int = Field(120, ge=1)
    cleanup_interval_seconds: int = Field(900, ge=1)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @field_validator("upload_dir", "result_dir", "work_dir", mode="after")
    @classmethod
    def absolute_runtime_path(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator("model_id", mode="after")
    @classmethod
    def validate_model_id(
        cls, value: Literal["microsoft/Mage-VL"] | Path
    ) -> Literal["microsoft/Mage-VL"] | Path:
        if value == OFFICIAL_MODEL_ID:
            return value
        path = Path(value).expanduser().resolve()
        if not path.is_dir():
            raise ValueError(
                f"model_id must be {OFFICIAL_MODEL_ID!r} or an existing local directory"
            )
        return path

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        for path in (self.upload_dir, self.result_dir, self.work_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()

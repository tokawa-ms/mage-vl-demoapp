from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from fastapi import UploadFile

from app.errors import UploadValidationError
from app.media import inspect_media, probe_video, store_upload
from app.schemas import AnalysisMode


@pytest.mark.asyncio
async def test_store_upload_uses_generated_safe_name(settings, jpeg_bytes):
    settings.ensure_directories()
    upload = UploadFile(filename="../../unsafe.jpg", file=__import__("io").BytesIO(jpeg_bytes))
    path, size = await store_upload(upload, settings)
    assert path.parent == settings.upload_dir
    assert path.name != "unsafe.jpg"
    assert path.suffix == ".jpg"
    assert size == len(jpeg_bytes)


@pytest.mark.asyncio
async def test_store_upload_rejects_oversize(settings):
    settings.ensure_directories()
    upload = UploadFile(
        filename="huge.mp4",
        file=__import__("io").BytesIO(b"x" * (settings.max_upload_bytes + 1)),
    )
    with pytest.raises(UploadValidationError, match="exceeds"):
        await store_upload(upload, settings)
    assert not list(settings.upload_dir.iterdir())


def test_image_validation_reads_actual_image(settings, jpeg_bytes):
    settings.ensure_directories()
    path = settings.upload_dir / "image.jpg"
    path.write_bytes(jpeg_bytes)
    metadata = inspect_media(
        path, "photo.jpg", "image/jpeg", len(jpeg_bytes), AnalysisMode.IMAGE, settings
    )
    assert (metadata.width, metadata.height, metadata.media_type) == (12, 8, "image")


def test_video_probe_parses_ffprobe_json(settings):
    payload = {
        "streams": [
            {
                "codec_name": "hevc",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30000/1001",
                "nb_frames": "90",
            }
        ],
        "format": {"duration": "3.003"},
    }

    def runner(command, **kwargs):
        assert command[0] == settings.ffprobe_path
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    result = probe_video(Path("clip.mp4"), settings, runner)
    assert result["codec"] == "hevc"
    assert result["frame_count"] == 90
    assert result["fps"] == pytest.approx(29.97, rel=1e-3)
    assert result["duration_seconds"] == pytest.approx(3.003)


def test_video_duration_limit_is_enforced(settings):
    settings.max_video_seconds = 2

    def runner(command, **kwargs):
        payload = {
            "streams": [{"width": 10, "height": 10, "avg_frame_rate": "1/1"}],
            "format": {"duration": "3"},
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    with pytest.raises(UploadValidationError, match="duration exceeds"):
        inspect_media(
            Path("clip.mp4"),
            "clip.mp4",
            "video/mp4",
            12,
            AnalysisMode.VIDEO_FRAMES,
            settings,
            runner,
        )

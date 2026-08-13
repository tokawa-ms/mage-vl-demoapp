from __future__ import annotations

import json
import math
import os
import subprocess
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from fastapi import UploadFile

from .errors import DependencyUnavailableError, UploadValidationError
from .schemas import AnalysisMode, MediaMetadata
from .settings import Settings

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def _safe_extension(filename: str | None) -> str:
    name = Path(filename or "").name
    suffix = Path(name).suffix.lower()
    if not suffix or suffix not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
        raise UploadValidationError("Unsupported media file extension")
    return suffix


async def store_upload(upload: UploadFile, settings: Settings) -> tuple[Path, int]:
    suffix = _safe_extension(upload.filename)
    destination = settings.upload_dir / f"{uuid4().hex}{suffix}"
    temporary = destination.with_suffix(destination.suffix + ".part")
    size = 0
    try:
        with temporary.open("xb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise UploadValidationError(
                        f"Upload exceeds {settings.max_upload_mb} MB limit"
                    )
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if size == 0:
            raise UploadValidationError("Uploaded file is empty")
        temporary.replace(destination)
        return destination, size
    except Exception:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


def _parse_fraction(value: str | None) -> float | None:
    if not value or value in {"0/0", "N/A"}:
        return None
    try:
        numerator, denominator = value.split("/", 1)
        parsed = float(numerator) / float(denominator)
        return parsed if math.isfinite(parsed) else None
    except (ValueError, ZeroDivisionError):
        return None


def probe_video(
    path: Path,
    settings: Settings,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    command = [
        settings.ffprobe_path,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,avg_frame_rate,nb_frames,duration:format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = runner(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=settings.subprocess_timeout_seconds,
        )
    except FileNotFoundError as error:
        raise DependencyUnavailableError("ffprobe is not installed or not on PATH") from error
    except (subprocess.SubprocessError, OSError) as error:
        raise UploadValidationError(f"ffprobe could not read the video: {error}") from error
    try:
        payload = json.loads(completed.stdout)
        stream = payload["streams"][0]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
        raise UploadValidationError("The upload contains no readable video stream") from error
    duration_value = stream.get("duration") or payload.get("format", {}).get("duration")
    try:
        duration = float(duration_value)
    except (TypeError, ValueError):
        duration = None
    if not stream.get("width") or not stream.get("height"):
        raise UploadValidationError("Video dimensions are unavailable")
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "duration_seconds": duration,
        "fps": _parse_fraction(stream.get("avg_frame_rate")),
        "frame_count": int(stream["nb_frames"]) if str(stream.get("nb_frames", "")).isdigit() else None,
        "codec": stream.get("codec_name"),
    }


def inspect_media(
    path: Path,
    original_filename: str,
    content_type: str | None,
    size: int,
    mode: AnalysisMode,
    settings: Settings,
    probe_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> MediaMetadata:
    suffix = path.suffix.lower()
    if mode == AnalysisMode.IMAGE:
        if suffix not in IMAGE_EXTENSIONS:
            raise UploadValidationError("Image mode requires a supported image file")
        try:
            from PIL import Image

            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                width, height = image.size
        except Exception as error:
            raise UploadValidationError("The upload is not a valid image") from error
        return MediaMetadata(
            media_type="image",
            filename=Path(original_filename).name,
            content_type=content_type,
            size_bytes=size,
            width=width,
            height=height,
        )
    if suffix not in VIDEO_EXTENSIONS:
        raise UploadValidationError("The selected mode requires a supported video file")
    details = probe_video(path, settings, probe_runner)
    duration = details["duration_seconds"]
    if duration is not None and duration > settings.max_video_seconds:
        raise UploadValidationError(
            f"Video duration exceeds {settings.max_video_seconds:g} second limit"
        )
    return MediaMetadata(
        media_type="video",
        filename=Path(original_filename).name,
        content_type=content_type,
        size_bytes=size,
        **details,
    )


def sample_video_frames(path: Path, num_frames: int) -> list[Any]:
    import cv2
    import numpy as np
    from PIL import Image

    capture = cv2.VideoCapture(str(path))
    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if frame_count <= 0:
            raise UploadValidationError(f"Could not read video: {path.name}")
        indices = np.linspace(0, frame_count - 1, min(num_frames, frame_count), dtype=int)
        frames = []
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                raise UploadValidationError(f"Could not decode frame {index}")
            frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        return frames
    finally:
        capture.release()

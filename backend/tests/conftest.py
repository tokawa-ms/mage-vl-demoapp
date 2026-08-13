from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from app.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        upload_dir=tmp_path / "uploads",
        result_dir=tmp_path / "results",
        work_dir=tmp_path / "work",
        max_upload_mb=1,
        cleanup_interval_seconds=3600,
    )


@pytest.fixture
def jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (12, 8), color=(20, 40, 60)).save(buffer, format="JPEG")
    return buffer.getvalue()

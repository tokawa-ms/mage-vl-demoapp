from __future__ import annotations

import asyncio

import pytest

from app.jobs import JobManager
from app.schemas import (
    AnalysisMode,
    AnalysisResult,
    AnalysisSettings,
    JobStatus,
    MediaMetadata,
)


class SuccessfulInference:
    def analyze(self, job, emit, cancelled):
        emit("progress", {"progress": 0.8, "message": "Generating"})
        return AnalysisResult(
            analysis_id=job.id,
            answer="done",
            settings=job.settings,
            media=job.media,
            metrics={},
        )


class OomOnceInference(SuccessfulInference):
    def __init__(self):
        self.calls = 0

    def analyze(self, job, emit, cancelled):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("CUDA out of memory")
        return super().analyze(job, emit, cancelled)


def metadata():
    return MediaMetadata(
        media_type="image", filename="x.jpg", size_bytes=3, width=1, height=1
    )


def analysis_settings():
    return AnalysisSettings(
        mode=AnalysisMode.IMAGE,
        question="What?",
        num_frames=16,
        max_pixels=10_000,
    )


@pytest.mark.asyncio
async def test_fifo_worker_persists_result(settings, tmp_path):
    settings.ensure_directories()
    manager = JobManager(settings, SuccessfulInference())
    await manager.start()
    try:
        media_path = settings.upload_dir / "x.jpg"
        media_path.write_bytes(b"abc")
        first = await manager.create(analysis_settings(), metadata(), media_path)
        second = await manager.create(analysis_settings(), metadata(), media_path)
        await asyncio.wait_for(manager.queue.join(), 2)
        assert first.status == JobStatus.COMPLETED
        assert second.status == JobStatus.COMPLETED
        assert manager.result(first.id).answer == "done"
        assert manager.result(second.id).answer == "done"
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_oom_retries_once_with_reduced_bounds(settings):
    settings.ensure_directories()
    inference = OomOnceInference()
    manager = JobManager(settings, inference)
    await manager.start()
    try:
        path = settings.upload_dir / "x.jpg"
        path.write_bytes(b"x")
        job = await manager.create(analysis_settings(), metadata(), path)
        await asyncio.wait_for(manager.queue.join(), 2)
        assert inference.calls == 2
        assert job.status == JobStatus.COMPLETED
        assert job.retry_count == 1
        assert job.settings.num_frames == 8
        assert job.settings.max_pixels == 5_000
        assert "out of memory" in manager.result(job.id).warnings[0].lower()
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_cancel_queued_job(settings):
    settings.ensure_directories()
    manager = JobManager(settings, SuccessfulInference())
    path = settings.upload_dir / "x.jpg"
    path.write_bytes(b"x")
    job = await manager.create(analysis_settings(), metadata(), path)
    manager.cancel(job.id)
    assert job.status == JobStatus.CANCELLED

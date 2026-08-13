from __future__ import annotations

import asyncio
import gc
import json
import shutil
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any, AsyncIterator
from uuid import uuid4

from .errors import CancelledError
from .inference import InferenceService, is_oom_error
from .schemas import (
    AnalysisJob,
    AnalysisResult,
    AnalysisSettings,
    JobStatus,
    MediaMetadata,
    utcnow,
)
from .settings import Settings


class JobManager:
    def __init__(self, settings: Settings, inference: InferenceService) -> None:
        self.settings = settings
        self.inference = inference
        self.jobs: dict[str, AnalysisJob] = {}
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._cleanup: asyncio.Task[None] | None = None
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._load_persisted_jobs()
        self._worker = asyncio.create_task(self._worker_loop(), name="mage-job-worker")
        self._cleanup = asyncio.create_task(self._cleanup_loop(), name="mage-cleanup-worker")

    async def stop(self) -> None:
        if self._worker:
            await self.queue.put(None)
            await self._worker
        if self._cleanup:
            self._cleanup.cancel()
            await asyncio.gather(self._cleanup, return_exceptions=True)

    async def create(
        self,
        settings: AnalysisSettings,
        media: MediaMetadata,
        media_path: Path,
    ) -> AnalysisJob:
        job_id = uuid4().hex
        job = AnalysisJob(
            id=job_id,
            status=JobStatus.QUEUED,
            message="Waiting for the inference worker",
            settings=settings,
            media=media,
            media_path=str(media_path),
            result_path=str(self.settings.result_dir / f"{job_id}.json"),
        )
        self.jobs[job_id] = job
        self._persist_job(job)
        self._publish(job_id, "status", self.public_job(job))
        await self.queue.put(job_id)
        return job

    def get(self, job_id: str) -> AnalysisJob | None:
        return self.jobs.get(job_id)

    def public_job(self, job: AnalysisJob) -> dict[str, Any]:
        data = job.model_dump(mode="json", exclude={"media_path", "result_path", "cancel_requested"})
        data["queue_position"] = self._queue_position(job.id) if job.status == JobStatus.QUEUED else None
        return data

    def _queue_position(self, job_id: str) -> int | None:
        queued = [
            job
            for job in self.jobs.values()
            if job.status == JobStatus.QUEUED
        ]
        queued.sort(key=lambda item: item.created_at)
        for index, job in enumerate(queued, start=1):
            if job.id == job_id:
                return index
        return None

    def result(self, job_id: str) -> AnalysisResult | None:
        job = self.jobs.get(job_id)
        if not job or job.status != JobStatus.COMPLETED:
            return None
        try:
            return AnalysisResult.model_validate_json(Path(job.result_path).read_text("utf-8"))
        except (OSError, ValueError):
            return None

    def cancel(self, job_id: str) -> AnalysisJob | None:
        job = self.jobs.get(job_id)
        if not job:
            return None
        if job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
            return job
        job.cancel_requested = True
        job.updated_at = utcnow()
        if job.status == JobStatus.QUEUED:
            job.status = JobStatus.CANCELLED
            job.completed_at = utcnow()
            job.message = "Cancelled before execution"
        else:
            job.message = "Cancellation requested"
        self._persist_job(job)
        self._publish(job_id, "status", self.public_job(job))
        return job

    async def events(self, job_id: str) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._subscribers[job_id].add(queue)
        history = list(self._history.get(job_id, []))
        terminal = bool(
            (job := self.jobs.get(job_id))
            and job.status
            in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
        )
        for event in history:
            yield event
        if terminal:
            self._subscribers[job_id].discard(queue)
            return
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield {"event": "ping", "data": {"timestamp": utcnow().isoformat()}}
                    continue
                yield event
                if event["event"] == "status" and event["data"].get("status") in {
                    JobStatus.COMPLETED,
                    JobStatus.FAILED,
                    JobStatus.CANCELLED,
                }:
                    return
        finally:
            self._subscribers[job_id].discard(queue)

    async def _worker_loop(self) -> None:
        while True:
            job_id = await self.queue.get()
            try:
                if job_id is None:
                    return
                job = self.jobs.get(job_id)
                if not job or job.status == JobStatus.CANCELLED:
                    continue
                await self._run(job)
            finally:
                self.queue.task_done()

    async def _run(self, job: AnalysisJob) -> None:
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        job.updated_at = utcnow()
        job.message = "Analysis started"
        self._persist_job(job)
        self._publish(job.id, "status", self.public_job(job))
        try:
            try:
                result = await asyncio.to_thread(
                    self.inference.analyze,
                    job,
                    lambda name, data: self._threadsafe_event(job.id, name, data),
                    lambda: job.cancel_requested,
                )
            except Exception as error:
                if not is_oom_error(error) or job.retry_count:
                    raise
                job.retry_count = 1
                job.settings = job.settings.model_copy(
                    update={
                        "num_frames": max(1, job.settings.num_frames // 2),
                        "max_pixels": max(256, job.settings.max_pixels // 2),
                    }
                )
                retry_warning = (
                    "CUDA out of memory; retried once with reduced num_frames "
                    f"({job.settings.num_frames}) and max_pixels ({job.settings.max_pixels})."
                )
                self._publish(job.id, "warning", {"message": retry_warning})
                gc.collect()
                try:
                    import torch

                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except (ImportError, AttributeError):
                    pass
                result = await asyncio.to_thread(
                    self.inference.analyze,
                    job,
                    lambda name, data: self._threadsafe_event(job.id, name, data),
                    lambda: job.cancel_requested,
                )
                result.warnings.insert(0, retry_warning)
            if job.cancel_requested:
                raise CancelledError("Analysis was cancelled")
            self._write_json_atomic(Path(job.result_path), result.model_dump(mode="json"))
            job.status = JobStatus.COMPLETED
            job.progress = 1
            job.message = "Analysis completed"
        except CancelledError:
            job.status = JobStatus.CANCELLED
            job.message = "Analysis cancelled"
        except Exception as error:
            job.status = JobStatus.FAILED
            job.error = f"{type(error).__name__}: {error}"
            job.message = "Analysis failed"
        finally:
            job.completed_at = utcnow()
            job.updated_at = utcnow()
            self._persist_job(job)
            self._publish(job.id, "status", self.public_job(job))

    def _threadsafe_event(self, job_id: str, name: str, data: dict[str, Any]) -> None:
        if self._loop:
            self._loop.call_soon_threadsafe(self._handle_event, job_id, name, data)

    def _handle_event(self, job_id: str, name: str, data: dict[str, Any]) -> None:
        job = self.jobs.get(job_id)
        if job and name == "progress":
            job.progress = min(1, max(job.progress, float(data.get("progress", 0))))
            job.message = str(data.get("message", job.message))
            job.updated_at = utcnow()
        self._publish(job_id, name, data)

    def _publish(self, job_id: str, name: str, data: dict[str, Any]) -> None:
        event = {"event": name, "data": data}
        history = self._history[job_id]
        history.append(event)
        if len(history) > 200:
            del history[:-200]
        for queue in tuple(self._subscribers.get(job_id, ())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def _job_path(self, job_id: str) -> Path:
        return self.settings.result_dir / f"{job_id}.job.json"

    def _persist_job(self, job: AnalysisJob) -> None:
        self._write_json_atomic(self._job_path(job.id), job.model_dump(mode="json"))

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(path)

    def _load_persisted_jobs(self) -> None:
        for path in self.settings.result_dir.glob("*.job.json"):
            try:
                job = AnalysisJob.model_validate_json(path.read_text("utf-8"))
                if job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
                    job.status = JobStatus.FAILED
                    job.error = "Backend restarted before analysis completed"
                    job.message = "Analysis interrupted by backend restart"
                    job.completed_at = utcnow()
                    self._persist_job(job)
                self.jobs[job.id] = job
            except (OSError, ValueError):
                continue

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.cleanup_interval_seconds)
            self.cleanup_expired()

    def cleanup_expired(self) -> None:
        cutoff = utcnow() - timedelta(hours=self.settings.job_retention_hours)
        for job_id, job in list(self.jobs.items()):
            timestamp = job.completed_at or job.updated_at
            if (
                job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
                and timestamp < cutoff
            ):
                Path(job.media_path).unlink(missing_ok=True)
                Path(job.result_path).unlink(missing_ok=True)
                self._job_path(job_id).unlink(missing_ok=True)
                shutil.rmtree(self.settings.work_dir / job_id, ignore_errors=True)
                self.jobs.pop(job_id, None)
                self._history.pop(job_id, None)

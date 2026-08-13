from __future__ import annotations

import json
import math
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from .errors import AppError, UploadValidationError
from .jobs import JobManager
from .media import inspect_media, store_upload
from .schemas import AnalysisCreated, AnalysisMode, AnalysisSettings, JobStatus

router = APIRouter()


def _manager(request: Request) -> JobManager:
    return request.app.state.job_manager


@router.post(
    "/api/analyses",
    response_model=AnalysisCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_analysis(
    request: Request,
    media: Annotated[UploadFile, File()],
    mode: Annotated[AnalysisMode, Form()],
    question: Annotated[str, Form()] = "Describe this media.",
    num_frames: Annotated[int, Form()] = 32,
    max_pixels: Annotated[int, Form()] = 150_000,
    max_new_tokens: Annotated[int, Form()] = 256,
    segment_sec: Annotated[float, Form()] = 8.0,
    gate_threshold: Annotated[float, Form()] = 0.5,
) -> AnalysisCreated:
    app_settings = request.app.state.settings
    try:
        analysis_settings = AnalysisSettings(
            mode=mode,
            question=question,
            num_frames=min(num_frames, app_settings.max_frames),
            max_pixels=min(max_pixels, app_settings.max_pixels),
            max_new_tokens=min(max_new_tokens, app_settings.max_new_tokens),
            segment_sec=segment_sec,
            gate_threshold=gate_threshold,
        )
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=json.loads(error.json())) from error
    path = None
    try:
        path, size = await store_upload(media, app_settings)
        metadata = inspect_media(
            path,
            media.filename or path.name,
            media.content_type,
            size,
            mode,
            app_settings,
        )
        if (
            mode == AnalysisMode.STREAMING
            and metadata.duration_seconds
            and math.ceil(metadata.duration_seconds / analysis_settings.segment_sec)
            > app_settings.max_streaming_segments
        ):
            raise UploadValidationError(
                "Streaming input exceeds the segment limit; shorten the video "
                f"or increase segment length (maximum {app_settings.max_streaming_segments} segments)"
            )
        job = await _manager(request).create(analysis_settings, metadata, path)
        return AnalysisCreated(id=job.id, status=job.status)
    except UploadValidationError as error:
        if path:
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(error)) from error
    except AppError as error:
        if path:
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/api/analyses/{analysis_id}")
async def get_analysis(analysis_id: str, request: Request) -> dict[str, Any]:
    manager = _manager(request)
    job = manager.get(analysis_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return manager.public_job(job)


@router.get("/api/analyses/{analysis_id}/result")
async def get_result(analysis_id: str, request: Request) -> dict[str, Any]:
    manager = _manager(request)
    job = manager.get(analysis_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if job.status == JobStatus.FAILED:
        raise HTTPException(status_code=409, detail=job.error or "Analysis failed")
    if job.status == JobStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="Analysis was cancelled")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=425, detail="Analysis is not complete")
    result = manager.result(analysis_id)
    if not result:
        raise HTTPException(status_code=500, detail="Persisted result is unavailable")
    return result.model_dump(mode="json")


@router.delete("/api/analyses/{analysis_id}")
async def cancel_analysis(analysis_id: str, request: Request) -> dict[str, Any]:
    manager = _manager(request)
    job = manager.cancel(analysis_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return manager.public_job(job)


@router.get("/api/analyses/{analysis_id}/events")
async def analysis_events(analysis_id: str, request: Request) -> StreamingResponse:
    manager = _manager(request)
    if not manager.get(analysis_id):
        raise HTTPException(status_code=404, detail="Analysis not found")

    async def stream():
        async for item in manager.events(analysis_id):
            yield (
                f"event: {item['event']}\n"
                f"data: {json.dumps(item['data'], ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

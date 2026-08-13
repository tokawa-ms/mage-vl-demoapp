from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .inference import InferenceService
from .jobs import JobManager
from .model import ModelManager
from .probes import dependency_capabilities
from .settings import Settings, get_settings


def create_app(
    settings: Settings | None = None,
    model_manager: ModelManager | None = None,
    inference_service: InferenceService | None = None,
) -> FastAPI:
    configured = settings or get_settings()
    models = model_manager or ModelManager(configured)
    inference = inference_service or InferenceService(configured, models)
    jobs = JobManager(configured, inference)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configured.ensure_directories()
        await jobs.start()
        if configured.preload_model:
            try:
                await asyncio.to_thread(models.load)
            except Exception:
                pass
        yield
        await jobs.stop()

    app = FastAPI(title="Mage-VL Studio API", version="1.0.0", lifespan=lifespan)
    app.state.settings = configured
    app.state.model_manager = models
    app.state.job_manager = jobs
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configured.cors_origins,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(request: Request):
        capabilities = dependency_capabilities(configured)
        model_status = request.app.state.model_manager.status()
        base_ready = (
            capabilities["python_modules"]["torch"]
            and capabilities["python_modules"]["transformers"]
            and capabilities["cuda"]["available"]
            and (
                configured.quantization != "4bit"
                or capabilities["python_modules"]["bitsandbytes"]
            )
        )
        ready = base_ready and model_status.state != "error"
        return {
            "status": "ready" if ready else "not_ready",
            "ready": ready,
            "model": model_status.model_dump(),
        }

    @app.get("/api/capabilities")
    async def capabilities():
        return dependency_capabilities(configured)

    @app.get("/api/model/status")
    async def model_status(request: Request):
        return request.app.state.model_manager.status()

    return app


app = create_app()

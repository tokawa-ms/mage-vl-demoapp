from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import AnalysisResult, MediaMetadata


class FakeModelManager:
    def status(self):
        from app.schemas import ModelStatus

        return ModelStatus(
            state="ready",
            model_id="fake",
            quantization="none",
            loaded=True,
            device="cpu",
        )


class FakeInference:
    def analyze(self, job, emit, cancelled):
        emit("progress", {"progress": 0.5, "message": "Halfway"})
        return AnalysisResult(
            analysis_id=job.id,
            answer="A synthetic answer",
            segments=[],
            metrics={"fake": True},
            warnings=[],
            settings=job.settings,
            media=job.media,
        )


def wait_for_terminal(client: TestClient, job_id: str) -> dict:
    for _ in range(100):
        response = client.get(f"/api/analyses/{job_id}")
        body = response.json()
        if body["status"] in {"completed", "failed", "cancelled"}:
            return body
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_health_and_image_analysis_contract(settings, jpeg_bytes):
    app = create_app(settings, FakeModelManager(), FakeInference())
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        created = client.post(
            "/api/analyses",
            files={"media": ("photo.jpg", jpeg_bytes, "image/jpeg")},
            data={
                "mode": "image",
                "question": "Describe it",
                "num_frames": "999",
                "max_pixels": "9999999",
                "max_new_tokens": "9999",
                "segment_sec": "4",
                "gate_threshold": "0.4",
            },
        )
        assert created.status_code == 202
        job_id = created.json()["id"]
        terminal = wait_for_terminal(client, job_id)
        assert terminal["status"] == "completed"
        result = client.get(f"/api/analyses/{job_id}/result")
        assert result.status_code == 200
        assert result.json()["answer"] == "A synthetic answer"
        assert result.json()["settings"]["num_frames"] == settings.max_frames
        assert result.json()["settings"]["max_pixels"] == settings.max_pixels
        with client.stream("GET", f"/api/analyses/{job_id}/events") as events:
            body = "".join(events.iter_text())
        assert "event: status" in body
        assert '"status": "completed"' in body


def test_invalid_media_is_rejected_and_cors_is_configured(settings):
    app = create_app(settings, FakeModelManager(), FakeInference())
    with TestClient(app) as client:
        response = client.post(
            "/api/analyses",
            files={"media": ("fake.jpg", b"not an image", "image/jpeg")},
            data={"mode": "image", "question": "x"},
        )
        assert response.status_code == 400
        cors = client.options(
            "/healthz",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert cors.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_missing_analysis_returns_404(settings):
    app = create_app(settings, FakeModelManager(), FakeInference())
    with TestClient(app) as client:
        assert client.get("/api/analyses/missing").status_code == 404
        assert client.get("/api/analyses/missing/events").status_code == 404


def test_invalid_numeric_settings_return_422(settings, jpeg_bytes):
    app = create_app(settings, FakeModelManager(), FakeInference())
    with TestClient(app) as client:
        response = client.post(
            "/api/analyses",
            files={"media": ("photo.jpg", jpeg_bytes, "image/jpeg")},
            data={"mode": "image", "question": "x", "num_frames": "0"},
        )
        assert response.status_code == 422


def test_streaming_segment_limit_is_enforced(settings, monkeypatch):
    settings.max_streaming_segments = 2
    monkeypatch.setattr(
        "app.api.inspect_media",
        lambda *args, **kwargs: MediaMetadata(
            media_type="video",
            filename="long.mp4",
            content_type="video/mp4",
            size_bytes=5,
            duration_seconds=30,
        ),
    )
    app = create_app(settings, FakeModelManager(), FakeInference())
    with TestClient(app) as client:
        response = client.post(
            "/api/analyses",
            files={"media": ("long.mp4", b"video", "video/mp4")},
            data={
                "mode": "streaming",
                "question": "Describe it",
                "segment_sec": "8",
            },
        )
        assert response.status_code == 400
        assert "segment limit" in response.json()["detail"]

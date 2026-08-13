from __future__ import annotations

import pytest

from app.errors import CancelledError
from app.inference import InferenceService, _generate
from app.schemas import AnalysisJob, AnalysisMode, AnalysisSettings, JobStatus, MediaMetadata


class Value:
    def to(self, *args, **kwargs):
        return self


class Processor:
    def __init__(self):
        self.calls = []

    def apply_chat_template(self, messages, **kwargs):
        return "prompt"

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return {"input_ids": Value(), "pixel_values": Value()}


class Model:
    device = "cuda:0"
    dtype = "bf16"


class Models:
    def local_model_path(self):
        return "C:\\model"


class GeneratingModel:
    def generate(self, **kwargs):
        stopped = kwargs["stopping_criteria"](
            kwargs["input_ids"],
            scores=None,
        )
        assert stopped.item() is True
        return kwargs["input_ids"]


class GeneratingProcessor:
    class Tokenizer:
        def decode(self, *args, **kwargs):
            return "unused"

    tokenizer = Tokenizer()


def job_for(mode, settings, path):
    return AnalysisJob(
        id="job",
        status=JobStatus.RUNNING,
        settings=AnalysisSettings(mode=mode, question="Describe", num_frames=12),
        media=MediaMetadata(
            media_type="video", filename="x.mp4", size_bytes=10, duration_seconds=2
        ),
        media_path=str(path),
        result_path=str(path.with_suffix(".json")),
    )


def test_traditional_codec_matches_official_adapter(settings, tmp_path, monkeypatch):
    processor = Processor()
    service = InferenceService(settings, Models())
    monkeypatch.setattr("app.inference._generate", lambda *args: "answer")
    answer, _, _, _ = service._offline(
        job_for(AnalysisMode.TRADITIONAL_CODEC, settings, tmp_path / "x.mp4"),
        Model(),
        processor,
        lambda *args: None,
        lambda: False,
    )
    call = processor.calls[0]
    assert answer == "answer"
    assert call["video_backend"] == "codec"
    assert call["codec_config"] == {
        "engine": "hevc",
        "target_canvas": 12,
        "patch": 16,
    }


def test_neural_codec_configures_bundled_dcvc_rt(settings, tmp_path, monkeypatch):
    processor = Processor()
    service = InferenceService(settings, Models())
    monkeypatch.setattr("app.inference._generate", lambda *args: "answer")
    service._offline(
        job_for(AnalysisMode.NEURAL_CODEC, settings, tmp_path / "x.mp4"),
        Model(),
        processor,
        lambda *args: None,
        lambda: False,
    )
    config = processor.calls[0]["codec_config"]
    assert config["engine"] == "dcvc-rt"
    assert config["dcvc"]["pkg_dir"].endswith("neural_codec")
    assert config["dcvc"]["device"] == "cuda:0"


def test_generation_stops_when_cancellation_is_requested():
    torch = pytest.importorskip("torch")
    checks = 0

    def cancelled():
        nonlocal checks
        checks += 1
        return checks >= 2

    with pytest.raises(CancelledError):
        _generate(
            GeneratingModel(),
            GeneratingProcessor(),
            {"input_ids": torch.ones((1, 2), dtype=torch.long)},
            128,
            cancelled,
        )

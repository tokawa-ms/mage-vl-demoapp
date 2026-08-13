from __future__ import annotations

import os
import math
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from .errors import CancelledError, InferenceError
from .media import sample_video_frames
from .model import ModelManager
from .schemas import AnalysisJob, AnalysisMode, AnalysisResult
from .settings import Settings

Emit = Callable[[str, dict[str, Any]], None]
IsCancelled = Callable[[], bool]


def is_oom_error(error: BaseException) -> bool:
    text = str(error).lower()
    return "out of memory" in text or "cuda error: out of memory" in text


def _check_cancelled(cancelled: IsCancelled) -> None:
    if cancelled():
        raise CancelledError("Analysis was cancelled")


def _gpu_memory_metrics() -> dict[str, float]:
    try:
        import torch

        if not torch.cuda.is_available():
            return {}
        return {
            "allocated_gb": round(torch.cuda.memory_allocated() / 2**30, 3),
            "reserved_gb": round(torch.cuda.memory_reserved() / 2**30, 3),
            "peak_allocated_gb": round(torch.cuda.max_memory_allocated() / 2**30, 3),
        }
    except (ImportError, RuntimeError):
        return {}


def _move_inputs(inputs: Any, model: Any) -> dict[str, Any]:
    device = getattr(model, "device", "cuda")
    dtype = getattr(model, "dtype", None)
    moved: dict[str, Any] = {}
    for key, value in dict(inputs).items():
        if not hasattr(value, "to"):
            moved[key] = value
        elif key == "pixel_values" and dtype is not None:
            moved[key] = value.to(device=device, dtype=dtype)
        else:
            moved[key] = value.to(device)
    return moved


def _prompt(processor: Any, media_type: str, question: str) -> str:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": media_type},
                {"type": "text", "text": question},
            ],
        }
    ]
    return processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )


def _generate(
    model: Any,
    processor: Any,
    inputs: dict[str, Any],
    max_tokens: int,
    cancelled: IsCancelled,
) -> str:
    try:
        import torch
        from transformers import StoppingCriteria, StoppingCriteriaList

        context = torch.inference_mode()

        class CancellationCriteria(StoppingCriteria):
            def __call__(
                self,
                input_ids: Any,
                scores: Any,
                **kwargs: Any,
            ) -> Any:
                return torch.full(
                    (input_ids.shape[0],),
                    cancelled(),
                    dtype=torch.bool,
                    device=input_ids.device,
                )

        stopping_criteria = StoppingCriteriaList([CancellationCriteria()])
    except ImportError:
        from contextlib import nullcontext

        context = nullcontext()
        stopping_criteria = None
    _check_cancelled(cancelled)
    with context:
        output = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            do_sample=False,
            stopping_criteria=stopping_criteria,
        )
    _check_cancelled(cancelled)
    prompt_length = inputs["input_ids"].shape[1]
    return processor.tokenizer.decode(
        output[0, prompt_length:], skip_special_tokens=True
    ).strip()


class InferenceService:
    def __init__(self, settings: Settings, model_manager: ModelManager) -> None:
        self.settings = settings
        self.model_manager = model_manager

    def analyze(
        self,
        job: AnalysisJob,
        emit: Emit,
        cancelled: IsCancelled,
    ) -> AnalysisResult:
        started = time.perf_counter()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
        except (ImportError, RuntimeError):
            pass
        _check_cancelled(cancelled)
        emit("progress", {"progress": 0.1, "message": "Loading model"})
        model, processor = self.model_manager.load()
        _check_cancelled(cancelled)
        if job.settings.mode == AnalysisMode.STREAMING:
            answer, segments, metrics, warnings = self._streaming(
                job, model, processor, emit, cancelled
            )
        else:
            answer, segments, metrics, warnings = self._offline(
                job, model, processor, emit, cancelled
            )
        metrics["elapsed_seconds"] = round(time.perf_counter() - started, 4)
        metrics["retry_count"] = job.retry_count
        metrics["gpu_memory"] = _gpu_memory_metrics()
        return AnalysisResult(
            analysis_id=job.id,
            answer=answer,
            segments=segments,
            metrics=metrics,
            warnings=warnings,
            settings=job.settings,
            media=job.media,
        )

    def _offline(
        self,
        job: AnalysisJob,
        model: Any,
        processor: Any,
        emit: Emit,
        cancelled: IsCancelled,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any], list[str]]:
        path = Path(job.media_path)
        mode = job.settings.mode
        media_type = "image" if mode == AnalysisMode.IMAGE else "video"
        text = _prompt(processor, media_type, job.settings.question)
        kwargs: dict[str, Any] = {
            "text": [text],
            "return_tensors": "pt",
        }
        emit("progress", {"progress": 0.35, "message": "Preparing media"})
        if mode == AnalysisMode.IMAGE:
            from PIL import Image

            with Image.open(path) as source:
                kwargs["images"] = [source.convert("RGB")]
                inputs = processor(**kwargs)
        elif mode == AnalysisMode.VIDEO_FRAMES:
            frames = sample_video_frames(path, job.settings.num_frames)
            kwargs.update(videos=[frames], padding=True)
            inputs = processor(**kwargs)
        else:
            codec_config: dict[str, Any] = {
                "engine": "hevc"
                if mode == AnalysisMode.TRADITIONAL_CODEC
                else "dcvc-rt",
                "target_canvas": job.settings.num_frames,
                "patch": 16,
            }
            if mode == AnalysisMode.NEURAL_CODEC:
                codec_config["dcvc"] = {
                    "pkg_dir": str(
                        Path(self.model_manager.local_model_path()) / "neural_codec"
                    ),
                    "device": str(getattr(model, "device", "cuda")),
                }
            kwargs.update(
                videos=[str(path)],
                video_backend="codec",
                max_pixels=job.settings.max_pixels,
                codec_config=codec_config,
                padding=True,
            )
            inputs = processor(**kwargs)
        _check_cancelled(cancelled)
        inputs = _move_inputs(inputs, model)
        emit("progress", {"progress": 0.7, "message": "Generating answer"})
        answer = _generate(
            model,
            processor,
            inputs,
            job.settings.max_new_tokens,
            cancelled,
        )
        _check_cancelled(cancelled)
        visual_tokens = None
        grid = inputs.get("image_grid_thw")
        if grid is not None:
            try:
                visual_tokens = int(grid.prod(dim=-1).sum().item())
            except Exception:
                pass
        return answer, [], {"visual_tokens": visual_tokens}, []

    def _extract_subclip(
        self, src: Path, start: float, duration: float, destination: Path
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".tmp_{destination.name}")
        command = [
            self.settings.ffmpeg_path,
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{max(0.0, start):.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(src),
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            str(temporary),
        ]
        try:
            subprocess.run(
                command,
                check=True,
                timeout=self.settings.subprocess_timeout_seconds,
                capture_output=True,
            )
            temporary.replace(destination)
            return destination
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def _streaming(
        self,
        job: AnalysisJob,
        model: Any,
        processor: Any,
        emit: Emit,
        cancelled: IsCancelled,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any], list[str]]:
        if not hasattr(model, "streammind_gate_forward_segments"):
            raise InferenceError(
                "Checkpoint does not expose streammind_gate_forward_segments()"
            )
        duration = job.media.duration_seconds
        if not duration:
            raise InferenceError("Streaming requires a known video duration")
        source = Path(job.media_path)
        clip_dir = self.settings.work_dir / job.id / "segments"
        os.environ.setdefault(
            "ONLINE_CODEC_CACHE_DIR", str(self.settings.work_dir / job.id / "codec")
        )
        prepared: list[dict[str, Any]] = []
        timestamps: list[tuple[float, float]] = []
        warnings: list[str] = []
        total = max(1, math.ceil(duration / job.settings.segment_sec))
        for index in range(total):
            _check_cancelled(cancelled)
            start = index * job.settings.segment_sec
            end = min(duration, start + job.settings.segment_sec)
            if start >= end:
                break
            destination = clip_dir / f"segment_{index:06d}.mp4"
            try:
                self._extract_subclip(source, start, end - start, destination)
                text = _prompt(processor, "video", job.settings.question)
                inputs = processor(
                    text=[text],
                    videos=[str(destination)],
                    video_backend="codec",
                    codec_config={"patch": 16, "max_pixels": job.settings.max_pixels},
                    max_pixels=job.settings.max_pixels,
                    return_tensors="pt",
                    padding=False,
                )
                prepared.append(_move_inputs(inputs, model))
                timestamps.append((start, end))
            except Exception as error:
                warning = f"Segment {start:.2f}-{end:.2f}s was skipped: {error}"
                warnings.append(warning)
                emit("warning", {"message": warning})
            emit(
                "progress",
                {
                    "progress": 0.1 + 0.45 * ((index + 1) / total),
                    "message": f"Prepared segment {index + 1}/{total}",
                },
            )
        if not prepared:
            raise InferenceError("No usable streaming segments were produced")
        visual_segments = [
            {
                key: segment[key]
                for key in ("pixel_values", "image_grid_thw", "patch_positions")
                if key in segment
            }
            for segment in prepared
        ]
        try:
            import torch

            with torch.inference_mode():
                logits = model.streammind_gate_forward_segments(visual_segments)[0]
            lengths = [
                int(segment["image_grid_thw"][:, 0].sum()) for segment in visual_segments
            ]
            boundaries = torch.tensor(lengths, device=logits.device).cumsum(0) - 1
            probabilities = (
                torch.softmax(logits[boundaries].float(), dim=-1)[:, 1].tolist()
            )
        except Exception as error:
            raise InferenceError(f"Cognition gate failed: {error}") from error
        segments: list[dict[str, Any]] = []
        answers: list[str] = []
        for index, ((start, end), inputs, probability) in enumerate(
            zip(timestamps, prepared, probabilities, strict=True)
        ):
            _check_cancelled(cancelled)
            spoke = probability >= job.settings.gate_threshold
            text = ""
            if spoke:
                text = _generate(
                    model,
                    processor,
                    inputs,
                    job.settings.max_new_tokens,
                    cancelled,
                )
                answers.append(f"[{start:.1f}-{end:.1f}s] {text}")
            segment = {
                "index": index,
                "start_seconds": start,
                "end_seconds": end,
                "gate_probability": round(float(probability), 6),
                "decision": "response" if spoke else "silence",
                "answer": text or None,
            }
            segments.append(segment)
            emit("segment", segment)
            emit(
                "progress",
                {
                    "progress": 0.55 + 0.45 * ((index + 1) / len(prepared)),
                    "message": f"Analyzed segment {index + 1}/{len(prepared)}",
                },
            )
        answer = "\n".join(answers) or "No segment crossed the cognition gate threshold."
        return (
            answer,
            segments,
            {
                "segments_total": len(segments),
                "segments_triggered": len(answers),
                "gate_threshold": job.settings.gate_threshold,
            },
            warnings,
        )

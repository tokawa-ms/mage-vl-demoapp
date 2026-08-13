from __future__ import annotations

import importlib.util
import shutil
from typing import Any

from .settings import Settings


def dependency_capabilities(settings: Settings) -> dict[str, Any]:
    python_modules = {
        name: importlib.util.find_spec(name) is not None
        for name in ("torch", "transformers", "bitsandbytes", "cv2", "PIL", "decord")
    }
    executables = {
        "ffmpeg": shutil.which(settings.ffmpeg_path) is not None,
        "ffprobe": shutil.which(settings.ffprobe_path) is not None,
        "cv-preinfer": shutil.which("cv-preinfer") is not None,
    }
    cuda: dict[str, Any] = {"available": False, "device_count": 0, "devices": []}
    if python_modules["torch"]:
        try:
            import torch

            cuda["available"] = bool(torch.cuda.is_available())
            if cuda["available"]:
                cuda["device_count"] = torch.cuda.device_count()
                for index in range(cuda["device_count"]):
                    props = torch.cuda.get_device_properties(index)
                    cuda["devices"].append(
                        {
                            "index": index,
                            "name": props.name,
                            "capability": list(torch.cuda.get_device_capability(index)),
                            "total_memory_bytes": props.total_memory,
                        }
                    )
        except Exception as error:
            cuda["error"] = str(error)
    base = (
        python_modules["torch"]
        and python_modules["transformers"]
        and cuda["available"]
        and (settings.quantization != "4bit" or python_modules["bitsandbytes"])
    )

    def mode(supported: bool, missing: str) -> dict[str, Any]:
        return {"supported": bool(supported), "reason": None if supported else missing}

    modes = {
        "image": mode(base and python_modules["PIL"], "CUDA, model dependencies, and Pillow are required"),
        "video_frames": mode(base and python_modules["cv2"], "CUDA, model dependencies, and OpenCV are required"),
        "traditional_codec": mode(
            base and executables["ffmpeg"] and executables["ffprobe"] and executables["cv-preinfer"],
            "CUDA, model dependencies, ffmpeg/ffprobe, and cv-preinfer are required",
        ),
        "neural_codec": mode(
            base and executables["ffmpeg"],
            "CUDA, model dependencies, ffmpeg, and checkpoint neural-codec assets are required",
        ),
        "streaming": mode(
            base and executables["ffmpeg"] and python_modules["decord"],
            "CUDA, model dependencies, ffmpeg, and Decord are required",
        ),
    }
    first_device = cuda["devices"][0] if cuda["devices"] else {}
    gpu = {
        "available": cuda["available"],
        "name": first_device.get("name"),
        "vram_total_gb": (
            round(first_device["total_memory_bytes"] / 2**30, 1)
            if first_device.get("total_memory_bytes")
            else None
        ),
    }
    return {
        "model": settings.model_id,
        "version": "1.0.0",
        "python_modules": python_modules,
        "executables": executables,
        "cuda": cuda,
        "gpu": gpu,
        "modes": modes,
    }

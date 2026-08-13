from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from .errors import ModelLoadError
from .schemas import ModelStatus
from .settings import Settings


class ModelManager:
    _instance: "ModelManager | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls, settings: Settings | None = None) -> "ModelManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, settings: Settings | None = None) -> None:
        if self._initialized:
            if settings is not None and self.model is None:
                self.settings = settings
                self.model_path = str(settings.model_id)
            return
        if settings is None:
            raise ValueError("Settings are required for first ModelManager initialization")
        self.settings = settings
        self.model: Any = None
        self.processor: Any = None
        self.model_path = str(settings.model_id)
        self.error: str | None = None
        self.state = "not_loaded"
        self._load_lock = threading.Lock()
        self._initialized = True

    @classmethod
    def reset_for_tests(cls) -> None:
        with cls._instance_lock:
            cls._instance = None

    def load(self) -> tuple[Any, Any]:
        if self.model is not None and self.processor is not None:
            return self.model, self.processor
        with self._load_lock:
            if self.model is not None and self.processor is not None:
                return self.model, self.processor
            self.state = "loading"
            self.error = None
            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoProcessor

                kwargs: dict[str, Any] = {
                    "trust_remote_code": True,
                    "device_map": "auto",
                    "torch_dtype": "auto",
                    "attn_implementation": "sdpa",
                }
                if self.settings.quantization == "4bit":
                    try:
                        from transformers import BitsAndBytesConfig
                    except ImportError as error:
                        raise ModelLoadError(
                            "4-bit quantization requires transformers BitsAndBytesConfig"
                        ) from error
                    compute_dtype = torch.float16
                    kwargs["quantization_config"] = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_compute_dtype=compute_dtype,
                        bnb_4bit_use_double_quant=True,
                    )
                self.processor = AutoProcessor.from_pretrained(
                    self.model_path,
                    revision=self.settings.model_revision,
                    trust_remote_code=True,
                )
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_path,
                    revision=self.settings.model_revision,
                    **kwargs,
                ).eval()
                self.state = "ready"
                return self.model, self.processor
            except ModelLoadError as error:
                self.state = "error"
                self.error = str(error)
                raise
            except ImportError as error:
                self.state = "error"
                self.error = str(error)
                raise ModelLoadError(
                    f"Model dependency is unavailable: {error.name or error}"
                ) from error
            except Exception as error:
                self.state = "error"
                self.error = str(error)
                raise ModelLoadError(
                    f"Could not load model '{self.settings.model_id}': {error}"
                ) from error

    def local_model_path(self) -> str:
        if Path(self.model_path).is_dir():
            return self.model_path
        try:
            from huggingface_hub import snapshot_download

            self.model_path = snapshot_download(
                str(self.settings.model_id),
                revision=self.settings.model_revision,
            )
            return self.model_path
        except Exception as error:
            raise ModelLoadError(f"Could not download neural codec package: {error}") from error

    def status(self) -> ModelStatus:
        device = None
        if self.model is not None:
            device = str(getattr(self.model, "device", "auto"))
        return ModelStatus(
            state=self.state,
            model_id=str(self.settings.model_id),
            quantization=self.settings.quantization,
            loaded=self.model is not None,
            device=device,
            error=self.error,
        )

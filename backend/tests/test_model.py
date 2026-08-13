from __future__ import annotations

import sys
import types

import pytest
from pydantic import ValidationError

from app.model import ModelManager
from app.settings import AUDITED_MODEL_REVISION, OFFICIAL_MODEL_ID, Settings


class FakeModel:
    device = "cuda:0"

    def eval(self):
        return self


def test_default_model_load_uses_nf4_and_trust_remote_code(settings, monkeypatch):
    calls = {}

    class AutoProcessor:
        @staticmethod
        def from_pretrained(model_id, **kwargs):
            calls["processor"] = (model_id, kwargs)
            return object()

    class AutoModel:
        @staticmethod
        def from_pretrained(model_id, **kwargs):
            calls["model"] = (model_id, kwargs)
            return FakeModel()

    class BitsAndBytesConfig:
        def __init__(self, **kwargs):
            calls["quantization"] = kwargs

    fake_transformers = types.ModuleType("transformers")
    fake_transformers.AutoProcessor = AutoProcessor
    fake_transformers.AutoModelForCausalLM = AutoModel
    fake_transformers.BitsAndBytesConfig = BitsAndBytesConfig
    fake_torch = types.ModuleType("torch")
    fake_torch.bfloat16 = "bf16"
    fake_torch.float16 = "fp16"
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    ModelManager.reset_for_tests()
    manager = ModelManager(settings)
    model, _ = manager.load()
    assert isinstance(model, FakeModel)
    assert calls["processor"][1]["trust_remote_code"] is True
    assert calls["processor"][1]["revision"] == AUDITED_MODEL_REVISION
    assert calls["model"][1]["trust_remote_code"] is True
    assert calls["model"][1]["revision"] == AUDITED_MODEL_REVISION
    assert calls["model"][1]["device_map"] == "auto"
    assert calls["model"][1]["attn_implementation"] == "sdpa"
    assert calls["quantization"] == {
        "load_in_4bit": True,
        "bnb_4bit_quant_type": "nf4",
        "bnb_4bit_compute_dtype": "fp16",
        "bnb_4bit_use_double_quant": True,
    }
    ModelManager.reset_for_tests()


def test_settings_reject_unapproved_remote_model_and_revision():
    with pytest.raises(ValidationError):
        Settings(model_id="other/model")
    with pytest.raises(ValidationError):
        Settings(model_revision="main")


def test_local_model_directory_is_supported(tmp_path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()

    settings = Settings(model_id=model_dir)

    ModelManager.reset_for_tests()
    manager = ModelManager(settings)
    assert manager.local_model_path() == str(model_dir.resolve())
    ModelManager.reset_for_tests()


def test_snapshot_download_uses_audited_revision(settings, monkeypatch):
    calls = {}

    def snapshot_download(model_id, **kwargs):
        calls["download"] = (model_id, kwargs)
        return "C:\\cached-model"

    fake_hub = types.ModuleType("huggingface_hub")
    fake_hub.snapshot_download = snapshot_download
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)

    ModelManager.reset_for_tests()
    manager = ModelManager(settings)
    assert manager.local_model_path() == "C:\\cached-model"
    assert calls["download"] == (
        OFFICIAL_MODEL_ID,
        {"revision": AUDITED_MODEL_REVISION},
    )
    ModelManager.reset_for_tests()

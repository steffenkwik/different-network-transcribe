"""P1-3 regression: performance settings must actually reach the engine.

`cpu_threads` and `compute_type` were configurable, validated, and surfaced as a
CPU preset long before anything passed them to WhisperModel, so choosing a preset
changed nothing at all.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import ClassVar

import pytest

from app.transcription.engine import EngineResult, FasterWhisperEngine, engine_version

pytestmark = pytest.mark.unit


class _Segment:
    def __init__(self, text: str) -> None:
        self.text = text


class _Info:
    language = "id"
    language_probability = 0.97


class _FakeModel:
    last_kwargs: ClassVar[dict[str, object]] = {}

    def __init__(self, path: str, **kwargs: object) -> None:
        self.path = path
        _FakeModel.last_kwargs = kwargs
        self.transcribe_kwargs: dict[str, object] = {}

    def transcribe(self, audio: str, **kwargs: object):
        self.transcribe_kwargs = kwargs
        return [_Segment(" halo "), _Segment(" dunia ")], _Info()


class _FakePipeline:
    def __init__(self, model: object) -> None:
        self.model = model
        self.transcribe_kwargs: dict[str, object] = {}

    def transcribe(self, audio: str, **kwargs: object):
        self.transcribe_kwargs = kwargs
        return [_Segment("batched")], _Info()


@pytest.fixture
def fake_faster_whisper(monkeypatch: pytest.MonkeyPatch):
    """Install a stand-in package so the contract is tested without 480 MB of weights."""
    module = types.ModuleType("faster_whisper")
    module.WhisperModel = _FakeModel  # type: ignore[attr-defined]
    module.BatchedInferencePipeline = lambda model: _FakePipeline(model)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", module)
    return module


def test_cpu_threads_and_compute_type_reach_the_model(fake_faster_whisper, tmp_path: Path) -> None:
    engine = FasterWhisperEngine(tmp_path / "small", cpu_threads=7, compute_type="int8", batched=False)
    engine.load()

    assert _FakeModel.last_kwargs["cpu_threads"] == 7
    assert _FakeModel.last_kwargs["compute_type"] == "int8"
    assert _FakeModel.last_kwargs["device"] == "cpu"


def test_batched_pipeline_is_used_and_receives_the_batch_size(
    fake_faster_whisper, tmp_path: Path
) -> None:
    engine = FasterWhisperEngine(tmp_path / "small", batched=True, batch_size=6)
    engine.load()
    result = engine.transcribe(tmp_path / "a.opus")

    assert isinstance(result, EngineResult)
    assert engine._pipeline is not None
    assert engine._pipeline.transcribe_kwargs["batch_size"] == 6
    assert result.raw_transcript == "batched"


def test_an_engine_without_batching_still_transcribes(
    fake_faster_whisper, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Batching is throughput, never a correctness requirement."""

    def explode(model: object) -> object:
        raise ImportError("this build has no batched inference")

    monkeypatch.setattr(fake_faster_whisper, "BatchedInferencePipeline", explode)
    engine = FasterWhisperEngine(tmp_path / "small", batched=True)
    engine.load()
    result = engine.transcribe(tmp_path / "a.opus")

    assert engine._pipeline is None
    assert result.raw_transcript == "halo dunia"


def test_task_and_language_are_forwarded_verbatim(fake_faster_whisper, tmp_path: Path) -> None:
    engine = FasterWhisperEngine(
        tmp_path / "small", language="auto", task="translate", batched=False
    )
    engine.load()
    engine.transcribe(tmp_path / "a.opus")

    assert engine._model.transcribe_kwargs["task"] == "translate"
    # "auto" means let Whisper detect, which the API spells as language=None.
    assert engine._model.transcribe_kwargs["language"] is None


def test_explicit_language_is_not_turned_into_detection(
    fake_faster_whisper, tmp_path: Path
) -> None:
    engine = FasterWhisperEngine(tmp_path / "small", language="id", batched=False)
    engine.load()
    engine.transcribe(tmp_path / "a.opus")

    assert engine._model.transcribe_kwargs["language"] == "id"


def test_model_is_loaded_exactly_once(fake_faster_whisper, tmp_path: Path) -> None:
    engine = FasterWhisperEngine(tmp_path / "small", batched=False)
    engine.load()
    first = engine._model
    engine.load()

    assert engine._model is first


def test_transcribe_before_load_is_refused(tmp_path: Path) -> None:
    engine = FasterWhisperEngine(tmp_path / "small")
    with pytest.raises(RuntimeError, match="belum dimuat"):
        engine.transcribe(tmp_path / "a.opus")


def test_engine_version_reports_the_installed_package() -> None:
    """A hard-coded version in attempt provenance would lie after any upgrade."""
    assert engine_version() != "unknown"
    assert engine_version()[0].isdigit()

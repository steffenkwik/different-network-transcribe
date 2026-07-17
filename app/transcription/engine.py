"""Local transcription-engine contract; no cloud API is permitted."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class EngineResult:
    raw_transcript: str
    normalized_transcript: str
    detected_language: str | None = "id"
    language_probability: float | None = 1.0
    segment_json: str = "[]"


class TranscriptionEngine(Protocol):
    def load(self) -> None: ...

    def transcribe(self, path: Path) -> EngineResult: ...


def engine_version() -> str:
    """Report the installed engine, so an attempt's provenance is never guessed."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("faster-whisper")
    except PackageNotFoundError:
        return "unknown"


class FasterWhisperEngine:
    """CPU adapter. Model loading is explicit and happens exactly once per worker."""

    def __init__(
        self,
        model_directory: Path,
        *,
        language: str = "id",
        task: str = "transcribe",
        beam_size: int = 5,
        temperature: float = 0.0,
        vad_filter: bool = True,
        condition_on_previous_text: bool = False,
        compute_type: str = "int8",
        cpu_threads: int = 0,
        batched: bool = True,
        batch_size: int = 8,
    ) -> None:
        self.model_directory = model_directory
        self.language = language
        self.task = task
        self.beam_size = beam_size
        self.temperature = temperature
        self.vad_filter = vad_filter
        self.condition_on_previous_text = condition_on_previous_text
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self.batched = batched
        self.batch_size = batch_size
        self._model: Any | None = None
        self._pipeline: Any | None = None

    def load(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        # cpu_threads and compute_type were configurable long before they were
        # honoured here, so the CPU preset in Settings changed nothing at all.
        self._model = WhisperModel(
            str(self.model_directory),
            device="cpu",
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
        )
        if self.batched:
            self._pipeline = self._build_pipeline(self._model)

    @staticmethod
    def _build_pipeline(model: Any) -> Any | None:
        """Wrap the model for batched inference, tolerating an engine without it.

        Batching is a throughput win, never a correctness requirement: if this
        build of faster-whisper cannot provide it, transcription must still run.
        """
        try:
            from faster_whisper import BatchedInferencePipeline

            return BatchedInferencePipeline(model=model)
        except Exception:
            return None

    def transcribe(self, path: Path) -> EngineResult:
        if self._model is None:
            raise RuntimeError("Model belum dimuat.")
        options: dict[str, Any] = {
            "language": None if self.language == "auto" else self.language,
            "task": self.task,
            "beam_size": self.beam_size,
            "temperature": self.temperature,
            "vad_filter": self.vad_filter,
            "condition_on_previous_text": self.condition_on_previous_text,
        }
        if self._pipeline is not None:
            segments, info = self._pipeline.transcribe(
                str(path), batch_size=self.batch_size, **options
            )
        else:
            segments, info = self._model.transcribe(str(path), **options)
        parts = [segment.text.strip() for segment in segments]
        text = " ".join(part for part in parts if part)
        return EngineResult(
            raw_transcript=text,
            normalized_transcript=text,
            detected_language=info.language,
            language_probability=info.language_probability,
        )

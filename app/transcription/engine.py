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


class FasterWhisperEngine:
    """CPU-only adapter. Model loading is explicit and happens exactly once per worker."""

    def __init__(self, model_directory: Path, *, language: str = "id") -> None:
        self.model_directory = model_directory
        self.language = language
        self._model: Any | None = None

    def load(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        self._model = WhisperModel(str(self.model_directory), device="cpu", compute_type="int8")

    def transcribe(self, path: Path) -> EngineResult:
        if self._model is None:
            raise RuntimeError("Model belum dimuat.")
        model = self._model
        segments, info = model.transcribe(
            str(path),
            language=None if self.language == "auto" else self.language,
            task="transcribe",
            beam_size=5,
            temperature=0.0,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        parts = [segment.text.strip() for segment in segments]
        text = " ".join(part for part in parts if part)
        return EngineResult(
            raw_transcript=text,
            normalized_transcript=text,
            detected_language=info.language,
            language_probability=info.language_probability,
        )

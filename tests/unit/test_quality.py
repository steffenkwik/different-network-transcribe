"""Quality flags are conservative and never penalise a short voice note alone."""

from __future__ import annotations

import pytest

from app.transcription.engine import EngineResult
from app.transcription.quality import assess

pytestmark = pytest.mark.unit


def _result(text: str, probability: float | None = 1.0) -> EngineResult:
    return EngineResult(text, text, language_probability=probability)


def test_empty_transcript_is_no_speech() -> None:
    verdict = assess(_result(""), 12.0)
    assert verdict.no_speech is True
    assert verdict.status == "Tidak Ada Suara"


def test_short_audio_is_not_automatically_flagged() -> None:
    assert assess(_result("ya"), 1.5).status == "Baik"


def test_long_audio_with_little_text_requires_review() -> None:
    verdict = assess(_result("ya"), 60.0)
    assert verdict.status == "Perlu Diperiksa"
    assert "long_audio_little_text" in verdict.reasons


def test_repeated_phrase_requires_review() -> None:
    verdict = assess(_result("halo halo halo halo halo halo"), 15.0)
    assert verdict.status == "Perlu Diperiksa"
    assert "repeated_phrase" in verdict.reasons


def test_low_language_probability_requires_review() -> None:
    verdict = assess(_result("teks normal", 0.2), 10.0)
    assert verdict.status == "Perlu Diperiksa"
    assert "low_language_probability" in verdict.reasons

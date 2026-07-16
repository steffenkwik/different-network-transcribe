"""Conservative local transcript-quality checks.

The checks flag records for review; they never invent a transcript and they do
not make a short recording suspicious merely because it is short.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.transcription.engine import EngineResult


@dataclass(frozen=True)
class QualityVerdict:
    status: str
    score: float
    reasons: tuple[str, ...]
    no_speech: bool = False


def assess(result: EngineResult, duration_seconds: float | None) -> QualityVerdict:
    text = result.normalized_transcript.strip()
    if not text:
        return QualityVerdict("Tidak Ada Suara", 1.0, ("empty_transcript",), no_speech=True)

    reasons: list[str] = []
    normalized_words = re.findall(r"\w+", text.casefold())
    if _has_repeated_phrase(normalized_words):
        reasons.append("repeated_phrase")
    # A very small amount of text can be suspicious for a long recording, but
    # a short voice note is not automatically a quality failure.
    if duration_seconds is not None and duration_seconds >= 45 and len(normalized_words) <= 3:
        reasons.append("long_audio_little_text")
    if result.language_probability is not None and result.language_probability < 0.50:
        reasons.append("low_language_probability")
    if reasons:
        return QualityVerdict("Perlu Diperiksa", 0.45, tuple(reasons))
    return QualityVerdict("Baik", 1.0, ())


def _has_repeated_phrase(words: list[str]) -> bool:
    if len(words) < 6:
        return False
    for width in range(1, min(5, len(words) // 2 + 1)):
        phrase = words[:width]
        repeats = 0
        for offset in range(0, len(words) - width + 1, width):
            if words[offset : offset + width] == phrase:
                repeats += 1
            else:
                break
        if repeats >= 3:
            return True
    return False

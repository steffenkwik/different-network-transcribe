"""Evidence-based audio-to-chat matching. It never invents sender metadata."""

from __future__ import annotations

from dataclasses import dataclass

AUTO_ASSIGN_THRESHOLD = 0.90


@dataclass(frozen=True)
class AudioCandidate:
    audio_file_id: int
    normalized_basename: str
    duration_seconds: float | None = None


@dataclass(frozen=True)
class VoiceReferenceCandidate:
    reference_id: int
    normalized_filename: str | None
    sender: str | None
    chat: str | None
    whatsapp_message_at: str | None
    is_duplicate_export: bool = False


@dataclass(frozen=True)
class MetadataMatch:
    audio_file_id: int
    reference_id: int | None
    match_status: str
    confidence: float
    selected: bool
    sender: str | None
    chat: str | None
    whatsapp_message_at: str | None
    candidate_reference_ids: tuple[int, ...]


def match_audio(
    audio: AudioCandidate,
    references: list[VoiceReferenceCandidate],
    *,
    threshold: float = AUTO_ASSIGN_THRESHOLD,
) -> MetadataMatch:
    """Return an explicit match state; low-confidence sender fields stay unknown."""
    filename_candidates = [
        reference
        for reference in references
        if reference.normalized_filename == audio.normalized_basename
    ]
    canonical_candidates = [
        candidate for candidate in filename_candidates if not candidate.is_duplicate_export
    ]

    if len(filename_candidates) == 1:
        candidate = filename_candidates[0]
        return _result(audio, candidate, "exact_unique", 1.0, threshold, (candidate.reference_id,))
    if len(filename_candidates) > 1 and len(canonical_candidates) == 1:
        candidate = canonical_candidates[0]
        return _result(
            audio,
            candidate,
            "exact_duplicate_export_resolved",
            0.95,
            threshold,
            tuple(item.reference_id for item in filename_candidates),
        )
    if len(filename_candidates) > 1:
        return MetadataMatch(
            audio_file_id=audio.audio_file_id,
            reference_id=None,
            match_status="exact_ambiguous",
            confidence=0.0,
            selected=False,
            sender=None,
            chat=None,
            whatsapp_message_at=None,
            candidate_reference_ids=tuple(item.reference_id for item in filename_candidates),
        )

    if any(reference.normalized_filename is None for reference in references):
        return MetadataMatch(
            audio_file_id=audio.audio_file_id,
            reference_id=None,
            match_status="filename_not_present",
            confidence=0.0,
            selected=False,
            sender=None,
            chat=None,
            whatsapp_message_at=None,
            candidate_reference_ids=(),
        )
    timestamp_candidates = [
        reference for reference in references if reference.whatsapp_message_at is not None
    ]
    if timestamp_candidates:
        # A timestamp can help a reviewer but is never proof of sender identity.
        return MetadataMatch(
            audio_file_id=audio.audio_file_id,
            reference_id=None,
            match_status="probable_timestamp_match",
            confidence=0.69,
            selected=False,
            sender=None,
            chat=None,
            whatsapp_message_at=None,
            candidate_reference_ids=tuple(item.reference_id for item in timestamp_candidates),
        )
    return MetadataMatch(
        audio_file_id=audio.audio_file_id,
        reference_id=None,
        match_status="unmatched",
        confidence=0.0,
        selected=False,
        sender=None,
        chat=None,
        whatsapp_message_at=None,
        candidate_reference_ids=(),
    )


def _result(
    audio: AudioCandidate,
    candidate: VoiceReferenceCandidate,
    status: str,
    confidence: float,
    threshold: float,
    candidates: tuple[int, ...],
) -> MetadataMatch:
    selected = confidence >= threshold
    return MetadataMatch(
        audio_file_id=audio.audio_file_id,
        reference_id=candidate.reference_id if selected else None,
        match_status=status,
        confidence=confidence,
        selected=selected,
        sender=candidate.sender if selected else None,
        chat=candidate.chat if selected else None,
        whatsapp_message_at=candidate.whatsapp_message_at if selected else None,
        candidate_reference_ids=candidates,
    )

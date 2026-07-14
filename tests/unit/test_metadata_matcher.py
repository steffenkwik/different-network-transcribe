"""Matching safety rules: ambiguity and incomplete evidence never get guessed."""

from __future__ import annotations

import pytest

from app.matching.metadata_matcher import AudioCandidate, VoiceReferenceCandidate, match_audio

pytestmark = [pytest.mark.unit]


def _audio(name: str = "ptt-a.opus") -> AudioCandidate:
    return AudioCandidate(audio_file_id=1, normalized_basename=name)


def _reference(
    reference_id: int, name: str | None = "ptt-a.opus", **kwargs: object
) -> VoiceReferenceCandidate:
    return VoiceReferenceCandidate(
        reference_id=reference_id,
        normalized_filename=name,
        sender=kwargs.get("sender", "Synthetic Sender"),
        chat=kwargs.get("chat", "Synthetic Chat"),
        whatsapp_message_at=kwargs.get("whatsapp_message_at", "2026-07-15T20:31:00"),
        is_duplicate_export=bool(kwargs.get("is_duplicate_export", False)),
    )


def test_exact_unique_match_auto_assigns_with_full_confidence() -> None:
    result = match_audio(_audio(), [_reference(10)])
    assert result.match_status == "exact_unique"
    assert result.confidence == 1.0
    assert result.selected is True
    assert result.sender == "Synthetic Sender"


def test_duplicate_export_copy_resolves_to_the_canonical_reference() -> None:
    result = match_audio(_audio(), [_reference(10), _reference(11, is_duplicate_export=True)])
    assert result.match_status == "exact_duplicate_export_resolved"
    assert result.confidence == 0.95
    assert result.reference_id == 10


def test_ambiguous_match_preserves_candidates_but_never_assigns_sender() -> None:
    result = match_audio(_audio(), [_reference(10), _reference(11)])
    assert result.match_status == "exact_ambiguous"
    assert result.selected is False
    assert result.sender is None
    assert result.candidate_reference_ids == (10, 11)


def test_filename_absent_is_unknown_not_a_guess() -> None:
    result = match_audio(_audio(), [_reference(10, None)])
    assert result.match_status == "filename_not_present"
    assert result.sender is None


def test_timestamp_evidence_never_reaches_auto_assign_threshold() -> None:
    result = match_audio(_audio("unmatched.opus"), [_reference(10)])
    assert result.match_status == "probable_timestamp_match"
    assert result.confidence < 0.90
    assert result.selected is False
    assert result.sender is None


def test_unmatched_audio_has_no_sender() -> None:
    result = match_audio(_audio("unmatched.opus"), [])
    assert result.match_status == "unmatched"
    assert result.sender is None

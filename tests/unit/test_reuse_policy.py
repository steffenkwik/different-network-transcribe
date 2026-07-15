"""No-repeat policy: only source integrity and explicit requests may defeat reuse."""

from __future__ import annotations

import inspect

import pytest

from app.services.reuse_policy import ReuseState, may_reuse, next_action
from app.transcription.compatibility import CompatibilityInputs, compatibility_key

pytestmark = [pytest.mark.acceptance]


def _complete(**changes: object) -> ReuseState:
    values: dict[str, object] = {
        "source_exists": True,
        "on_disk_sha256": "same",
        "stored_sha256": "same",
        "completed_transcript_exists": True,
        "preferred_transcript_valid": True,
        "explicit_reprocess_pending": False,
    }
    values.update(changes)
    return ReuseState(**values)  # type: ignore[arg-type]


def test_completed_unchanged_source_is_skipped_without_inference() -> None:
    assert may_reuse(_complete()) is True
    assert next_action(_complete()) == "skipped_complete"


@pytest.mark.parametrize(
    "changes, action",
    [
        ({"source_exists": False}, "missing_source"),
        ({"on_disk_sha256": "changed"}, "stale_source_changed"),
        ({"completed_transcript_exists": False}, "claimable"),
        ({"preferred_transcript_valid": False}, "claimable"),
        ({"explicit_reprocess_pending": True}, "claimable"),
    ],
)
def test_closed_reprocess_trigger_list(changes: dict[str, object], action: str) -> None:
    assert next_action(_complete(**changes)) == action


def test_provenance_key_changes_with_settings_but_does_not_define_reuse() -> None:
    baseline = CompatibilityInputs(
        "faster-whisper",
        "1",
        "small",
        "hash",
        "id",
        "transcribe",
        "int8",
        5,
        0.0,
        True,
        False,
        "same",
    )
    changed = CompatibilityInputs(
        "faster-whisper",
        "1",
        "medium",
        "hash2",
        "id",
        "transcribe",
        "int8",
        8,
        0.2,
        True,
        False,
        "same",
    )
    assert compatibility_key(baseline) != compatibility_key(changed)
    assert may_reuse(_complete()) is True


def test_reuse_function_can_never_consult_the_provenance_key() -> None:
    assert "compat" not in inspect.getsource(may_reuse).lower()

"""The single no-repeat decision point for completed source versions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReuseState:
    source_exists: bool
    on_disk_sha256: str | None
    stored_sha256: str | None
    completed_transcript_exists: bool
    preferred_transcript_valid: bool
    explicit_reprocess_pending: bool


def may_reuse(state: ReuseState) -> bool:
    """True means skip inference. Settings/model differences deliberately do not appear here."""
    if not state.source_exists:
        return False
    if state.on_disk_sha256 != state.stored_sha256:
        return False
    if not state.completed_transcript_exists:
        return False
    if not state.preferred_transcript_valid:
        return False
    return not state.explicit_reprocess_pending


def next_action(state: ReuseState) -> str:
    if may_reuse(state):
        return "skipped_complete"
    if not state.source_exists:
        return "missing_source"
    if state.on_disk_sha256 != state.stored_sha256:
        return "stale_source_changed"
    return "claimable"

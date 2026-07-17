"""P0-3 regression: progress must describe the session, never all-time history."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.worker_status import (
    STATUS_SCHEMA,
    SessionProgress,
    format_duration,
    is_live,
    progress_percent,
    read_status,
    status_text,
)

pytestmark = pytest.mark.unit


def test_fresh_session_on_an_archive_with_history_starts_at_zero_percent() -> None:
    """The bug: 500 old completions + 20 new files rendered as 96% before any work."""
    status = {
        "schema": STATUS_SCHEMA,
        "state": "running",
        "session": {"total": 20, "done": 0, "failed": 0},
        "counts": {"queued": 20, "completed": 500, "failed": 0},
    }
    assert progress_percent(status) == 0


def test_progress_counts_failed_files_as_finished_work() -> None:
    status = {"state": "running", "session": {"total": 4, "done": 2, "failed": 1}}
    assert progress_percent(status) == 75


def test_legacy_schema_one_file_reports_zero_instead_of_the_old_lie() -> None:
    legacy = {"schema": 1, "state": "running", "counts": {"queued": 1, "completed": 99}}
    assert progress_percent(legacy) == 0


def test_progress_never_exceeds_one_hundred_percent() -> None:
    status = {"state": "running", "session": {"total": 2, "done": 5, "failed": 0}}
    assert progress_percent(status) == 100


def test_session_progress_tracks_average_and_eta() -> None:
    progress = SessionProgress(total=10)
    assert progress.avg_seconds_per_file() is None
    assert progress.eta_seconds() is None
    progress.start_file("voice-1.opus")
    assert progress.current_file == "voice-1.opus"
    progress.record_finished(10.0)
    progress.record_finished(20.0)
    assert progress.current_file is None
    assert progress.avg_seconds_per_file() == 15.0
    assert progress.remaining == 8
    assert progress.eta_seconds() == 120.0


def test_session_progress_counts_failures_separately_but_in_the_average() -> None:
    progress = SessionProgress(total=3)
    progress.record_finished(4.0, failed=True)
    progress.record_finished(8.0)
    assert (progress.done, progress.failed, progress.finished) == (1, 1, 2)
    assert progress.avg_seconds_per_file() == 6.0


def test_eta_is_absent_once_the_session_is_drained() -> None:
    progress = SessionProgress(total=1)
    progress.record_finished(5.0)
    assert progress.eta_seconds() is None


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "kurang dari 1 menit"),
        (59, "kurang dari 1 menit"),
        (60, "1 menit"),
        (600, "10 menit"),
        (3600, "1 jam"),
        (7800, "2 jam 10 menit"),
        (None, None),
    ],
)
def test_format_duration_is_coarse_and_indonesian(seconds, expected) -> None:
    assert format_duration(seconds) == expected


def test_status_text_reports_session_position_file_and_eta() -> None:
    text = status_text(
        {
            "state": "running",
            "session": {
                "total": 20,
                "done": 3,
                "failed": 0,
                "current_file": "voice-4.opus",
                "eta_seconds": 600,
            },
        }
    )
    assert "3/20 file" in text
    assert "voice-4.opus" in text
    assert "sisa ±10 menit" in text


def test_status_text_surfaces_a_safe_failure_message_verbatim() -> None:
    assert status_text({"state": "failed", "last_safe_message": "Model rusak."}) == "Model rusak."


def test_live_states_exclude_terminal_ones() -> None:
    assert is_live({"state": "running"})
    assert is_live({"state": "paused"})
    assert not is_live({"state": "finished"})
    assert not is_live({"state": "stopped"})
    assert not is_live({"state": "failed"})


def test_read_status_tolerates_missing_and_partial_files(tmp_path: Path) -> None:
    missing = tmp_path / "absent.json"
    assert read_status(missing) is None
    truncated = tmp_path / "partial.json"
    truncated.write_text('{"state": "run', encoding="utf-8")
    assert read_status(truncated) is None
    valid = tmp_path / "ok.json"
    valid.write_text(json.dumps({"state": "running"}), encoding="utf-8")
    assert read_status(valid) == {"state": "running"}

"""Phase 3 scanner tests use temporary synthetic bytes only, never real media."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.database.connection import open_connection
from app.database.migrations import MigrationRunner
from app.services.discovery_service import DiscoveryService

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.unit]


@pytest.fixture
def connection(tmp_path: Path):
    database_file = tmp_path / "data" / "Database" / "test.sqlite3"
    MigrationRunner(
        database_file, REPO_ROOT / "migrations", tmp_path / "data" / "Backups"
    ).migrate()
    connection = open_connection(database_file)
    try:
        yield connection
    finally:
        connection.close()


def _service(connection):
    return DiscoveryService(connection, duration_probe=lambda _: 1.25)


def _write(root: Path, relative: str, content: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _audio_count(connection) -> int:
    return int(connection.execute("SELECT COUNT(*) FROM audio_files").fetchone()[0])


def test_repeated_scan_creates_zero_new_audio_records(connection, tmp_path: Path) -> None:
    root = tmp_path / "source"
    _write(root, "one.opus", b"synthetic-one")
    _write(root, "nested/two.opus", b"synthetic-two")

    first = _service(connection).scan_audio_root(root)
    second = _service(connection).scan_audio_root(root)

    assert first.discovered == 2
    assert second.discovered == 0
    assert second.unchanged == 2
    assert _audio_count(connection) == 2
    assert connection.execute("SELECT COUNT(*) FROM transcription_attempts").fetchone()[0] == 0


def test_move_relinks_by_sha256_and_preserves_completed_state(connection, tmp_path: Path) -> None:
    root = tmp_path / "source"
    original = _write(root, "before/voice.opus", b"same-synthetic-bytes")
    service = _service(connection)
    service.scan_audio_root(root)
    original_row = connection.execute("SELECT id FROM audio_files").fetchone()
    connection.execute(
        "UPDATE audio_files SET current_state = 'completed_preferred' WHERE id = ?",
        (original_row["id"],),
    )

    moved = root / "after" / "renamed.opus"
    moved.parent.mkdir(parents=True)
    original.rename(moved)  # Simulates a user's move; DiscoveryService never moves sources.
    summary = service.scan_audio_root(root)

    row = connection.execute(
        "SELECT id, current_relative_path, current_state FROM audio_files"
    ).fetchone()
    assert summary.relinked == 1
    assert _audio_count(connection) == 1
    assert row["id"] == original_row["id"]
    assert row["current_relative_path"] == "after/renamed.opus"
    assert row["current_state"] == "completed_preferred"
    assert connection.execute("SELECT COUNT(*) FROM audio_path_history").fetchone()[0] == 2


def test_changed_bytes_create_a_new_source_version_without_retranscribing(
    connection, tmp_path: Path
) -> None:
    root = tmp_path / "source"
    file = _write(root, "voice.opus", b"before")
    service = _service(connection)
    service.scan_audio_root(root)
    file.write_bytes(b"after")  # Simulates an external source replacement.

    summary = service.scan_audio_root(root)
    row = connection.execute("SELECT current_state FROM audio_files").fetchone()
    versions = connection.execute(
        "SELECT sha256, is_current FROM audio_source_versions ORDER BY id"
    ).fetchall()
    assert summary.source_changed == 1
    assert row["current_state"] == "stale_source_changed"
    assert len(versions) == 2
    assert [version["is_current"] for version in versions] == [0, 1]
    assert connection.execute("SELECT COUNT(*) FROM transcription_attempts").fetchone()[0] == 0


def test_scanning_does_not_change_source_bytes(connection, tmp_path: Path) -> None:
    root = tmp_path / "source"
    source = _write(root, "read-only.opus", b"do-not-change")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    _service(connection).scan_audio_root(root)
    after = hashlib.sha256(source.read_bytes()).hexdigest()
    assert before == after


def test_same_basename_different_bytes_stay_separate_and_are_flagged_as_duplicates(
    connection, tmp_path: Path
) -> None:
    root = tmp_path / "source"
    _write(root, "a/PTT-1.opus", b"first")
    _write(root, "b/PTT-1.opus", b"second")
    summary = _service(connection).scan_audio_root(root)
    rows = connection.execute("SELECT id, duplicate_group FROM audio_files ORDER BY id").fetchall()
    assert summary.discovered == 2
    assert _audio_count(connection) == 2
    assert rows[0]["duplicate_group"] == rows[1]["duplicate_group"] == "basename:ptt-1.opus"


def test_zero_byte_input_is_recorded_but_never_given_a_source_version(
    connection, tmp_path: Path
) -> None:
    root = tmp_path / "source"
    _write(root, "empty.opus", b"")
    summary = _service(connection).scan_audio_root(root)
    row = connection.execute(
        "SELECT readable, zero_byte, current_source_version_id FROM audio_files"
    ).fetchone()
    assert summary.zero_byte == 1
    assert row["readable"] == 1
    assert row["zero_byte"] == 1
    assert row["current_source_version_id"] is None


def test_one_decode_error_does_not_stop_the_rest_of_the_scan(connection, tmp_path: Path) -> None:
    root = tmp_path / "source"
    _write(root, "bad.opus", b"bad")
    _write(root, "good.opus", b"good")

    def duration_probe(path: Path) -> float:
        if path.name == "bad.opus":
            raise RuntimeError("synthetic decode error")
        return 2.0

    summary = DiscoveryService(connection, duration_probe=duration_probe).scan_audio_root(root)
    rows = connection.execute(
        "SELECT basename, readable FROM audio_files ORDER BY basename"
    ).fetchall()
    assert summary.discovered == 2
    assert summary.unreadable == 1
    assert [(row["basename"], row["readable"]) for row in rows] == [
        ("bad.opus", 0),
        ("good.opus", 1),
    ]

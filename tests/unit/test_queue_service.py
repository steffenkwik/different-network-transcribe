"""Acceptance coverage for the queue-preparation no-repeat chokepoint."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.database.connection import open_connection
from app.database.migrations import MigrationRunner
from app.services.queue_service import QueueService

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.acceptance]


def test_restart_rescan_of_completed_sources_creates_zero_attempts_and_zero_queue(tmp_path: Path) -> None:
    database = tmp_path / "data" / "Database" / "test.sqlite3"
    MigrationRunner(database, REPO_ROOT / "migrations", tmp_path / "backups").migrate()
    source = tmp_path / "source"
    source.mkdir()
    connection = open_connection(database)
    try:
        root_id = connection.execute(
            "INSERT INTO source_roots(kind,original_path,normalized_path,created_at) VALUES ('audio',?,?, 't')",
            (str(source), str(source).casefold()),
        ).lastrowid
        for index in range(20):
            content = f"synthetic-{index}".encode()
            name = f"voice-{index}.opus"
            (source / name).write_bytes(content)
            audio_id = connection.execute(
                """INSERT INTO audio_files(stable_file_id,source_root_id,current_relative_path,basename,
                   normalized_basename,extension,size_bytes,first_discovered_at,last_seen_at,current_state,
                   readable,zero_byte,created_at,updated_at) VALUES (?,?,?,?,?,'.opus',?,'t','t',
                   'completed_preferred',1,0,'t','t')""",
                (f"audio-{index}", root_id, name, name, name, len(content)),
            ).lastrowid
            version_id = connection.execute(
                "INSERT INTO audio_source_versions(audio_file_id,size_bytes,sha256,discovered_at) VALUES (?,?,?, 't')",
                (audio_id, len(content), hashlib.sha256(content).hexdigest()),
            ).lastrowid
            attempt_id = connection.execute(
                """INSERT INTO transcription_attempts(audio_file_id,source_version_id,model_name,engine_name,
                   engine_version,language,settings_json,compat_key,attempt_number,state,raw_transcript,created_at)
                   VALUES (?,?,'small','fake','1','id','{}','fixed',1,'completed','done','t')""",
                (audio_id, version_id),
            ).lastrowid
            connection.execute(
                "UPDATE audio_files SET current_source_version_id=?, preferred_transcript_id=? WHERE id=?",
                (version_id, attempt_id, audio_id),
            )

        first = QueueService(connection).prepare()
        second = QueueService(connection).prepare()
        assert first.skipped_complete == second.skipped_complete == 20
        assert first.queued == second.queued == 0
        assert connection.execute("SELECT COUNT(*) FROM transcription_attempts").fetchone()[0] == 20
        assert connection.execute("SELECT COUNT(*) FROM audio_files WHERE current_state='queued'").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM processing_events WHERE event_type='skipped_complete'"
        ).fetchone()[0] == 40
    finally:
        connection.close()


def _scanned_archive(tmp_path: Path, count: int):
    """Discover real files so size and mtime are recorded the way a user's scan does."""
    from app.services.discovery_service import DiscoveryService

    database = tmp_path / "data" / "Database" / "test.sqlite3"
    MigrationRunner(database, REPO_ROOT / "migrations", tmp_path / "backups").migrate()
    source = tmp_path / "source"
    source.mkdir()
    for index in range(count):
        (source / f"voice-{index}.opus").write_bytes(f"synthetic-{index}".encode())
    connection = open_connection(database)
    DiscoveryService(connection, duration_probe=lambda _: 3.0).scan_audio_root(source)
    return connection, source


def test_unchanged_sources_are_not_rehashed_on_every_start(tmp_path: Path) -> None:
    """P1-2 regression: re-reading every byte of the archive delayed each start.

    On a 13,000-file collection this ran before the first voice note could be
    transcribed, which read as a freeze.
    """
    connection, _ = _scanned_archive(tmp_path, 6)
    try:
        # The scan already recorded each identity, so preparation re-reads
        # nothing at all: not on the first start, and not on any later one.
        first = QueueService(connection).prepare()
        assert first.queued == 6
        assert first.rehashed == 0

        second = QueueService(connection).prepare()

        assert second.queued == 6
        assert second.rehashed == 0
    finally:
        connection.close()


def test_a_changed_source_is_still_detected_without_trusting_the_stored_hash(
    tmp_path: Path,
) -> None:
    """Skipping the hash must never weaken change detection."""
    import os
    import time

    connection, source = _scanned_archive(tmp_path, 3)
    try:
        QueueService(connection).prepare()
        victim = source / "voice-1.opus"
        victim.write_bytes(b"completely-different-content-of-another-length")
        # Move mtime clearly outside the recorded second.
        future = time.time() + 5
        os.utime(victim, (future, future))

        summary = QueueService(connection).prepare()

        assert summary.rehashed == 1
        row = connection.execute(
            "SELECT current_state FROM audio_files WHERE basename = 'voice-1.opus'"
        ).fetchone()
        assert str(row["current_state"]) == "stale_source_changed"
    finally:
        connection.close()


def test_preparation_reports_progress_for_a_long_archive(tmp_path: Path) -> None:
    connection, _ = _scanned_archive(tmp_path, 4)
    try:
        seen: list[tuple[int, int]] = []
        QueueService(connection).prepare(progress=lambda done, total: seen.append((done, total)))
        assert seen[0] == (0, 4)
        assert seen[-1] == (4, 4)
    finally:
        connection.close()


def test_explicitly_excluded_source_is_never_queued_on_restart(tmp_path: Path) -> None:
    database = tmp_path / "data" / "Database" / "test.sqlite3"
    MigrationRunner(database, REPO_ROOT / "migrations", tmp_path / "backups").migrate()
    source = tmp_path / "source"
    source.mkdir()
    audio = source / "leave-out.opus"
    audio.write_bytes(b"synthetic leave out")
    connection = open_connection(database)
    try:
        root_id = int(
            connection.execute(
                "INSERT INTO source_roots(kind, original_path, normalized_path, created_at) VALUES ('audio', ?, ?, 't')",
                (str(source), str(source).casefold()),
            ).lastrowid
        )
        audio_id = int(
            connection.execute(
                """INSERT INTO audio_files(stable_file_id, source_root_id, current_relative_path, basename,
                   normalized_basename, extension, size_bytes, first_discovered_at, last_seen_at, current_state,
                   transcription_enabled, readable, zero_byte, created_at, updated_at)
                   VALUES ('excluded', ?, 'leave-out.opus', 'leave-out.opus', 'leave-out.opus', '.opus', ?, 't', 't',
                   'excluded', 0, 1, 0, 't', 't')""",
                (root_id, audio.stat().st_size),
            ).lastrowid
        )
        version_id = int(
            connection.execute(
                "INSERT INTO audio_source_versions(audio_file_id, size_bytes, sha256, discovered_at) VALUES (?, ?, ?, 't')",
                (audio_id, audio.stat().st_size, hashlib.sha256(audio.read_bytes()).hexdigest()),
            ).lastrowid
        )
        connection.execute(
            "UPDATE audio_files SET current_source_version_id = ? WHERE id = ?", (version_id, audio_id)
        )
        prepared = QueueService(connection).prepare()
        assert prepared.queued == 0
        assert connection.execute("SELECT current_state FROM audio_files WHERE id = ?", (audio_id,)).fetchone()[0] == "excluded"
    finally:
        connection.close()

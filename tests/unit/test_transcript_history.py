"""Explicit history deletion must preserve source evidence and prevent requeue."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.database.connection import open_connection
from app.database.migrations import MigrationRunner
from app.database.repositories import TranscriptHistoryRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.unit, pytest.mark.db]


def test_clear_selected_history_keeps_audio_and_metadata_but_removes_derived_text(tmp_path: Path) -> None:
    database = tmp_path / "Database" / "test.sqlite3"
    MigrationRunner(database, REPO_ROOT / "migrations", tmp_path / "Backups").migrate()
    connection = open_connection(database)
    try:
        root = int(
            connection.execute(
                "INSERT INTO source_roots(kind, original_path, normalized_path, created_at) "
                "VALUES ('audio', 'X:/source', 'x:/source', 't')"
            ).lastrowid
        )
        audio = int(
            connection.execute(
                """INSERT INTO audio_files(stable_file_id, source_root_id, current_relative_path, basename,
                   normalized_basename, extension, size_bytes, first_discovered_at, last_seen_at,
                   current_state, created_at, updated_at)
                   VALUES ('stable', ?, 'one.opus', 'one.opus', 'one.opus', '.opus', 1, 't', 't',
                   'completed_preferred', 't', 't')""",
                (root,),
            ).lastrowid
        )
        version = int(
            connection.execute(
                "INSERT INTO audio_source_versions(audio_file_id, size_bytes, sha256, discovered_at) "
                "VALUES (?, 1, 'hash', 't')",
                (audio,),
            ).lastrowid
        )
        attempt = int(
            connection.execute(
                """INSERT INTO transcription_attempts(audio_file_id, source_version_id, model_name, engine_name,
                   engine_version, language, settings_json, compat_key, attempt_number, state,
                   normalized_transcript, created_at)
                   VALUES (?, ?, 'high', 'fw', '1', 'id', '{}', 'key', 1, 'completed', 'isi rahasia', 't')""",
                (audio, version),
            ).lastrowid
        )
        manual = int(
            connection.execute(
                """INSERT INTO manual_transcripts(audio_file_id, based_on_attempt_id, text, created_at, updated_at)
                   VALUES (?, ?, 'koreksi', 't', 't')""",
                (audio, attempt),
            ).lastrowid
        )
        connection.execute(
            "UPDATE audio_files SET current_source_version_id = ?, preferred_transcript_id = ?, "
            "preferred_manual_transcript_id = ? WHERE id = ?",
            (version, attempt, manual, audio),
        )
        connection.execute("INSERT INTO transcript_fts(rowid, text) VALUES (?, 'isi rahasia')", (audio,))
        connection.execute("INSERT INTO transcript_fts_map(rowid, audio_file_id) VALUES (?, ?)", (audio, audio))

        assert TranscriptHistoryRepository(connection).clear_selected([audio]) == 1

        row = connection.execute(
            "SELECT basename, sha256, current_state, transcription_enabled, preferred_transcript_id, "
            "preferred_manual_transcript_id FROM audio_files WHERE id = ?", (audio,)
        ).fetchone()
        assert row["basename"] == "one.opus"
        source_hash = connection.execute(
            "SELECT sha256 FROM audio_source_versions WHERE id = ?", (version,)
        ).fetchone()["sha256"]
        assert source_hash == "hash"  # source identity remains intact
        assert row["current_state"] == "discovered"
        assert row["transcription_enabled"] == 0
        assert row["preferred_transcript_id"] is None
        assert row["preferred_manual_transcript_id"] is None
        assert connection.execute("SELECT COUNT(*) FROM audio_source_versions WHERE audio_file_id = ?", (audio,)).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM transcription_attempts WHERE audio_file_id = ?", (audio,)).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM manual_transcripts WHERE audio_file_id = ?", (audio,)).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM transcript_fts_map WHERE audio_file_id = ?", (audio,)).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM processing_events WHERE audio_file_id = ? AND event_type = 'history_cleared'", (audio,)).fetchone()[0] == 1
    finally:
        connection.close()


def test_clear_selected_history_ignores_empty_selection(tmp_path: Path) -> None:
    database = tmp_path / "Database" / "test.sqlite3"
    MigrationRunner(database, REPO_ROOT / "migrations", tmp_path / "Backups").migrate()
    connection = open_connection(database)
    try:
        assert TranscriptHistoryRepository(connection).clear_selected([]) == 0
    finally:
        connection.close()

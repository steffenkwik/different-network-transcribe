"""P0-5 regression: the search index must forget replaced transcripts.

`transcript_fts` is a contentless FTS5 table. Before `contentless_delete=1` an
`INSERT OR REPLACE` added the new tokens but could not remove the old ones, so
searching transcript bodies matched text that no longer existed anywhere.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from app.database.connection import open_connection
from app.database.migrations import MigrationRunner
from app.paths import DataPaths
from app.services.application_service import ApplicationService

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.unit]


def test_sqlite_supports_contentless_delete() -> None:
    """Guard the runtime requirement rather than discovering it at a user's desk."""
    assert tuple(int(part) for part in sqlite3.sqlite_version.split(".")) >= (3, 43, 0), (
        f"SQLite {sqlite3.sqlite_version} cannot delete from a contentless FTS5 table; "
        "transcript search would silently return replaced text."
    )


def _service_with_transcript(tmp_path: Path, text: str) -> tuple[ApplicationService, int]:
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    source = tmp_path / "source"
    source.mkdir()
    content = b"seed-voice-note"
    (source / "voice.opus").write_bytes(content)
    service.save_audio_root(source)
    service.scan_audio()

    connection = open_connection(paths.database_file)
    try:
        audio_id = int(connection.execute("SELECT id FROM audio_files LIMIT 1").fetchone()[0])
        version_id = connection.execute(
            "INSERT INTO audio_source_versions(audio_file_id, size_bytes, sha256, discovered_at) VALUES (?, ?, ?, 't')",
            (audio_id, len(content), hashlib.sha256(content).hexdigest()),
        ).lastrowid
        connection.execute(
            "UPDATE audio_files SET current_source_version_id = ? WHERE id = ?",
            (version_id, audio_id),
        )
        attempt_id = _insert_attempt(connection, audio_id, version_id, text, attempt_number=1)
        connection.execute(
            "UPDATE audio_files SET preferred_transcript_id = ?, current_state = 'completed_preferred' WHERE id = ?",
            (attempt_id, audio_id),
        )
        connection.execute(
            "INSERT OR REPLACE INTO transcript_fts(rowid, text) VALUES (?, ?)", (audio_id, text)
        )
        connection.execute(
            "INSERT INTO transcript_fts_map(rowid, audio_file_id) VALUES (?, ?) "
            "ON CONFLICT(audio_file_id) DO UPDATE SET rowid = excluded.rowid",
            (audio_id, audio_id),
        )
        connection.commit()
    finally:
        connection.close()
    return service, audio_id


def _insert_attempt(
    connection: sqlite3.Connection,
    audio_id: int,
    version_id: int,
    text: str,
    *,
    attempt_number: int,
) -> int:
    cursor = connection.execute(
        """INSERT INTO transcription_attempts(audio_file_id, source_version_id, model_name,
               engine_name, engine_version, language, settings_json, compat_key, attempt_number,
               state, started_at, completed_at, created_at, raw_transcript, normalized_transcript)
           VALUES (?, ?, 'small', 'faster-whisper', '1.1.1', 'id', '{}', ?, ?, 'completed',
                   't', 't', 't', ?, ?)""",
        (audio_id, version_id, f"compat-{attempt_number}", attempt_number, text, text),
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def test_reprocessed_transcript_drops_the_previous_text_from_search(tmp_path: Path) -> None:
    service, audio_id = _service_with_transcript(tmp_path, "kucing tidur di halaman")
    assert service.transcript_page(limit=10, transcript_query="kucing").total == 1

    # Simulate a second attempt replacing the preferred transcript.
    connection = open_connection(service.paths.database_file)
    try:
        version_id = int(
            connection.execute(
                "SELECT current_source_version_id FROM audio_files WHERE id = ?", (audio_id,)
            ).fetchone()[0]
        )
        new_text = "anjing berlari di taman"
        attempt_id = _insert_attempt(connection, audio_id, version_id, new_text, attempt_number=2)
        connection.execute(
            "UPDATE audio_files SET preferred_transcript_id = ? WHERE id = ?", (attempt_id, audio_id)
        )
        connection.execute(
            "INSERT OR REPLACE INTO transcript_fts(rowid, text) VALUES (?, ?)", (audio_id, new_text)
        )
        connection.commit()
    finally:
        connection.close()

    assert service.transcript_page(limit=10, transcript_query="anjing").total == 1
    assert service.transcript_page(limit=10, transcript_query="kucing").total == 0


def test_manual_correction_drops_the_engine_text_from_search(tmp_path: Path) -> None:
    service, audio_id = _service_with_transcript(tmp_path, "salah dengar sepenuhnya")
    assert service.transcript_page(limit=10, transcript_query="salah").total == 1

    service.save_manual_transcript(audio_id, text="koreksi manusia yang benar", verified=True)

    assert service.transcript_page(limit=10, transcript_query="koreksi").total == 1
    assert service.transcript_page(limit=10, transcript_query="salah").total == 0


def test_cleared_history_removes_the_row_from_search(tmp_path: Path) -> None:
    service, audio_id = _service_with_transcript(tmp_path, "rahasia yang dihapus")
    assert service.transcript_page(limit=10, transcript_query="rahasia").total == 1

    assert service.clear_transcript_history([audio_id]) == 1

    assert service.transcript_page(limit=10, transcript_query="rahasia").total == 0


def test_clearing_one_record_leaves_other_transcripts_searchable(tmp_path: Path) -> None:
    """A targeted delete must not disturb the rest of the index."""
    service, first_id = _service_with_transcript(tmp_path, "pertama tetap ada")
    connection = open_connection(service.paths.database_file)
    try:
        root_id = int(connection.execute("SELECT id FROM source_roots LIMIT 1").fetchone()[0])
        content = b"second-voice-note"
        (tmp_path / "source" / "voice-2.opus").write_bytes(content)
        second_id = connection.execute(
            """INSERT INTO audio_files(stable_file_id, source_root_id, current_relative_path,
                   basename, normalized_basename, extension, size_bytes, first_discovered_at,
                   last_seen_at, current_state, created_at, updated_at)
               VALUES ('second', ?, 'voice-2.opus', 'voice-2.opus', 'voice-2.opus', '.opus',
                       ?, 't', 't', 'completed_preferred', 't', 't')""",
            (root_id, len(content)),
        ).lastrowid
        assert second_id is not None
        version_id = connection.execute(
            "INSERT INTO audio_source_versions(audio_file_id, size_bytes, sha256, discovered_at) VALUES (?, ?, ?, 't')",
            (second_id, len(content), hashlib.sha256(content).hexdigest()),
        ).lastrowid
        connection.execute(
            "UPDATE audio_files SET current_source_version_id = ? WHERE id = ?",
            (version_id, second_id),
        )
        attempt_id = _insert_attempt(
            connection, int(second_id), int(version_id or 0), "kedua juga ada", attempt_number=1
        )
        connection.execute(
            "UPDATE audio_files SET preferred_transcript_id = ? WHERE id = ?", (attempt_id, second_id)
        )
        connection.execute(
            "INSERT OR REPLACE INTO transcript_fts(rowid, text) VALUES (?, ?)",
            (second_id, "kedua juga ada"),
        )
        connection.execute(
            "INSERT INTO transcript_fts_map(rowid, audio_file_id) VALUES (?, ?)",
            (second_id, second_id),
        )
        connection.commit()
    finally:
        connection.close()

    assert service.clear_transcript_history([first_id]) == 1

    assert service.transcript_page(limit=10, transcript_query="pertama").total == 0
    assert service.transcript_page(limit=10, transcript_query="kedua").total == 1


def test_migration_rebuilds_a_legacy_index_that_could_not_forget(tmp_path: Path) -> None:
    """An existing v0.2.0 database is upgraded without retranscribing anything."""
    database = tmp_path / "Database" / "legacy.sqlite3"
    database.parent.mkdir(parents=True)
    runner = MigrationRunner(database, REPO_ROOT / "migrations", tmp_path / "Backups")
    runner.migrate()

    connection = open_connection(database)
    try:
        definition = str(
            connection.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'transcript_fts'"
            ).fetchone()[0]
        )
        assert "contentless_delete=1" in definition
        # Prove the live table can now forget a replaced row.
        connection.execute("INSERT OR REPLACE INTO transcript_fts(rowid, text) VALUES (1, 'lama')")
        connection.execute("INSERT OR REPLACE INTO transcript_fts(rowid, text) VALUES (1, 'baru')")
        connection.commit()
        stale = connection.execute(
            "SELECT COUNT(*) FROM transcript_fts WHERE transcript_fts MATCH 'lama'"
        ).fetchone()[0]
        fresh = connection.execute(
            "SELECT COUNT(*) FROM transcript_fts WHERE transcript_fts MATCH 'baru'"
        ).fetchone()[0]
        assert (stale, fresh) == (0, 1)
    finally:
        connection.close()

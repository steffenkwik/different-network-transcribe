"""Phase 2 database gate: schema, migration safety, WAL and 13k paging."""

from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path

import pytest

from app.database.connection import (
    integrity_check,
    open_connection,
    quick_check,
    transaction,
)
from app.database.migrations import MigrationError, MigrationRunner, backup_database
from app.database.repositories import SettingsRepository, TranscriptRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "migrations"
pytestmark = [pytest.mark.db]


@pytest.fixture
def database_paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "Database" / "test.sqlite3", tmp_path / "Backups"


@pytest.fixture
def migrated_database(database_paths: tuple[Path, Path]) -> Path:
    database_file, backups_dir = database_paths
    MigrationRunner(database_file, MIGRATIONS, backups_dir).migrate()
    return database_file


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def _insert_root(connection: sqlite3.Connection) -> int:
    cursor = connection.execute(
        """
        INSERT INTO source_roots(kind, original_path, normalized_path, created_at)
        VALUES ('audio', 'X:/synthetic', 'x:/synthetic', '2026-07-15T00:00:00+07:00')
        """
    )
    return int(cursor.lastrowid)


def _insert_audio_rows(connection: sqlite3.Connection, count: int) -> None:
    root_id = _insert_root(connection)
    rows = [
        (
            f"synthetic-{index:05d}",
            root_id,
            f"folder/{index:05d}.opus",
            f"PTT-{index:05d}.opus",
            f"ptt-{index:05d}.opus",
            ".opus",
            index + 1,
            "2026-07-15T00:00:00+07:00",
            "2026-07-15T00:00:00+07:00",
            "queued" if index % 2 else "completed_preferred",
            "2026-07-15T00:00:00+07:00",
            "2026-07-15T00:00:00+07:00",
        )
        for index in range(count)
    ]
    with transaction(connection, immediate=True):
        connection.executemany(
            """
            INSERT INTO audio_files(
                stable_file_id, source_root_id, current_relative_path, basename,
                normalized_basename, extension, size_bytes, first_discovered_at,
                last_seen_at, current_state, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def test_initial_migration_creates_every_required_table(migrated_database: Path) -> None:
    connection = open_connection(migrated_database)
    try:
        expected = {
            "app_schema_migrations",
            "source_roots",
            "audio_files",
            "audio_path_history",
            "audio_source_versions",
            "chat_exports",
            "chat_voice_references",
            "metadata_matches",
            "manual_metadata_overrides",
            "transcription_attempts",
            "manual_transcripts",
            "processing_events",
            "worker_sessions",
            "worker_commands",
            "export_runs",
            "backups",
            "settings",
            "transcript_fts",
            "transcript_fts_map",
        }
        assert expected <= _tables(connection)
        assert connection.execute("SELECT COUNT(*) FROM app_schema_migrations").fetchone()[0] == 5
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(audio_files)")
        }
        assert "preferred_manual_transcript_id" in columns
        assert "transcription_enabled" in columns
        assert quick_check(connection) == "ok"
    finally:
        connection.close()


def test_migration_is_idempotent_and_backs_up_existing_schema(
    database_paths: tuple[Path, Path],
) -> None:
    database_file, backups_dir = database_paths
    runner = MigrationRunner(database_file, MIGRATIONS, backups_dir)
    assert [item.version for item in runner.migrate()] == [1, 2, 3, 4, 5]
    assert runner.migrate() == []
    # Simulate a future database at 0001 and prove the runner snapshots it
    # before applying the pending 0002 migration.
    connection = open_connection(database_file)
    try:
        connection.execute("DELETE FROM app_schema_migrations WHERE version = 2")
        connection.execute("DROP INDEX idx_audio_state_basename")
        connection.execute("DROP INDEX idx_chat_exports_duplicate")
        connection.execute("DROP INDEX idx_worker_sessions_heartbeat")
    finally:
        connection.close()
    assert [item.version for item in runner.migrate()] == [2]
    assert list(backups_dir.glob("pre-migration-*.sqlite3"))


def test_checksum_tampering_is_refused(database_paths: tuple[Path, Path], tmp_path: Path) -> None:
    database_file, backups_dir = database_paths
    copied_migrations = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS, copied_migrations)
    runner = MigrationRunner(database_file, copied_migrations, backups_dir)
    runner.migrate()
    migration = copied_migrations / "0001_initial.sql"
    migration.write_text(
        migration.read_text(encoding="utf-8") + "\n-- tampered\n", encoding="utf-8"
    )
    with pytest.raises(MigrationError, match="Checksum"):
        runner.migrate()


def test_wal_foreign_keys_and_integrity_are_configured(migrated_database: Path) -> None:
    connection = open_connection(migrated_database)
    try:
        assert str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"
        assert int(connection.execute("PRAGMA foreign_keys").fetchone()[0]) == 1
        assert int(connection.execute("PRAGMA busy_timeout").fetchone()[0]) == 5000
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO audio_files(stable_file_id, source_root_id, current_relative_path, basename, "
                "normalized_basename, extension, size_bytes, first_discovered_at, last_seen_at, current_state, "
                "created_at, updated_at) VALUES ('orphan', 999, 'a', 'a', 'a', '.opus', 1, 'x', 'x', 'queued', 'x', 'x')"
            )
        assert integrity_check(connection) == "ok"
    finally:
        connection.close()


def test_completed_attempt_text_is_immutable(migrated_database: Path) -> None:
    connection = open_connection(migrated_database)
    try:
        root_id = _insert_root(connection)
        audio_id = int(
            connection.execute(
                """INSERT INTO audio_files(stable_file_id, source_root_id, current_relative_path, basename,
                   normalized_basename, extension, size_bytes, first_discovered_at, last_seen_at, current_state,
                   created_at, updated_at) VALUES ('a', ?, 'a.opus', 'a.opus', 'a.opus', '.opus', 1, 't', 't',
                   'completed_preferred', 't', 't')""",
                (root_id,),
            ).lastrowid
        )
        version_id = int(
            connection.execute(
                "INSERT INTO audio_source_versions(audio_file_id, size_bytes, sha256, discovered_at) VALUES (?, 1, 'a', 't')",
                (audio_id,),
            ).lastrowid
        )
        attempt_id = int(
            connection.execute(
                """INSERT INTO transcription_attempts(audio_file_id, source_version_id, model_name, engine_name,
                   engine_version, language, settings_json, compat_key, attempt_number, state, raw_transcript,
                   created_at) VALUES (?, ?, 'small', 'fw', '1', 'id', '{}', 'k', 1, 'completed', 'awal', 't')""",
                (audio_id, version_id),
            ).lastrowid
        )
        connection.execute(
            "UPDATE audio_files SET current_source_version_id = ?, preferred_transcript_id = ? WHERE id = ?",
            (version_id, attempt_id, audio_id),
        )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE transcription_attempts SET raw_transcript = 'diubah' WHERE id = ?",
                (attempt_id,),
            )
    finally:
        connection.close()


def test_fts5_is_available_and_searchable(migrated_database: Path) -> None:
    connection = open_connection(migrated_database)
    try:
        connection.execute(
            "INSERT INTO transcript_fts(rowid, text) VALUES (1, ?)", ("rapat desain halaman",)
        )
        found = connection.execute(
            "SELECT rowid FROM transcript_fts WHERE transcript_fts MATCH ?", ("desain",)
        ).fetchall()
        assert [row["rowid"] for row in found] == [1]
    finally:
        connection.close()


def test_fts_backfill_migration_indexes_existing_preferred_transcript(
    database_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    database_file, backups_dir = database_paths
    legacy_migrations = tmp_path / "legacy-migrations"
    shutil.copytree(MIGRATIONS, legacy_migrations)
    (legacy_migrations / "0004_backfill_transcript_fts.sql").unlink()
    MigrationRunner(database_file, legacy_migrations, backups_dir).migrate()
    connection = open_connection(database_file)
    try:
        root = _insert_root(connection)
        audio = int(
            connection.execute(
                """INSERT INTO audio_files(stable_file_id, source_root_id, current_relative_path, basename,
                   normalized_basename, extension, size_bytes, first_discovered_at, last_seen_at, current_state,
                   created_at, updated_at) VALUES ('fts-audio', ?, 'a.opus', 'a.opus', 'a.opus', '.opus', 1,
                   't', 't', 'completed_preferred', 't', 't')""",
                (root,),
            ).lastrowid
        )
        version = int(
            connection.execute(
                "INSERT INTO audio_source_versions(audio_file_id, size_bytes, sha256, discovered_at) VALUES (?, 1, 'fts', 't')",
                (audio,),
            ).lastrowid
        )
        attempt = int(
            connection.execute(
                """INSERT INTO transcription_attempts(audio_file_id, source_version_id, model_name, engine_name,
                   engine_version, language, settings_json, compat_key, attempt_number, state,
                   normalized_transcript, created_at) VALUES (?, ?, 'small', 'fw', '1', 'id', '{}', 'k', 1,
                   'completed', 'pencarian khusus', 't')""",
                (audio, version),
            ).lastrowid
        )
        connection.execute(
            "UPDATE audio_files SET current_source_version_id = ?, preferred_transcript_id = ? WHERE id = ?",
            (version, attempt, audio),
        )
    finally:
        connection.close()
    assert [item.version for item in MigrationRunner(database_file, MIGRATIONS, backups_dir).migrate()] == [4]
    indexed = open_connection(database_file, read_only=True)
    try:
        assert indexed.execute(
            "SELECT COUNT(*) FROM transcript_fts WHERE transcript_fts MATCH 'khusus'"
        ).fetchone()[0] == 1
        assert indexed.execute("SELECT audio_file_id FROM transcript_fts_map").fetchone()[0] == audio
        page = TranscriptRepository(indexed).list_page(limit=10, transcript_query="khusus")
        assert page.total == 1
        assert int(page.rows[0]["id"]) == audio
    finally:
        indexed.close()


@pytest.mark.perf
@pytest.mark.slow
def test_13000_synthetic_records_page_within_acceptance_threshold(migrated_database: Path) -> None:
    connection = open_connection(migrated_database)
    try:
        started = time.perf_counter()
        _insert_audio_rows(connection, 13_000)
        insert_seconds = time.perf_counter() - started
        repository = TranscriptRepository(connection)

        started = time.perf_counter()
        first = repository.list_page(limit=100)
        first_page_seconds = time.perf_counter() - started

        started = time.perf_counter()
        page = repository.list_page(limit=100, offset=6_000)
        page_seconds = time.perf_counter() - started

        started = time.perf_counter()
        filtered = repository.list_page(limit=100, basename_query="ptt-120")
        filter_seconds = time.perf_counter() - started

        assert first.total == 13_000
        assert len(first.rows) == len(page.rows) == 100
        assert filtered.total == 100
        assert "raw_transcript" not in first.rows[0]
        assert insert_seconds < 10.0
        assert first_page_seconds < 1.0
        assert page_seconds < 0.5
        assert filter_seconds < 1.0
        print(
            "PERF 13000: "
            f"insert={insert_seconds:.3f}s first_page={first_page_seconds:.3f}s "
            f"page_6000={page_seconds:.3f}s filter={filter_seconds:.3f}s"
        )
    finally:
        connection.close()


def test_list_page_is_paged_and_does_not_load_transcript_bodies(migrated_database: Path) -> None:
    connection = open_connection(migrated_database)
    try:
        _insert_audio_rows(connection, 250)
        page = TranscriptRepository(connection).list_page(limit=25, offset=50, state="queued")
        assert page.total == 125
        assert len(page.rows) == 25
        column_names = set(page.rows[0].keys())
        assert "raw_transcript" not in column_names
        assert "normalized_transcript" not in column_names
    finally:
        connection.close()


def test_settings_repository_is_parameterised_and_roundtrips(migrated_database: Path) -> None:
    connection = open_connection(migrated_database)
    try:
        settings = SettingsRepository(connection)
        settings.set("theme", '"dark"')
        settings.set("theme", '"system"')
        assert settings.get("theme") == '"system"'
    finally:
        connection.close()


def test_backup_api_captures_a_consistent_database(migrated_database: Path, tmp_path: Path) -> None:
    connection = open_connection(migrated_database)
    try:
        _insert_audio_rows(connection, 2)
    finally:
        connection.close()
    backup = backup_database(migrated_database, tmp_path / "Backups", label="test")
    snapshot = open_connection(backup, read_only=True)
    try:
        assert snapshot.execute("SELECT COUNT(*) FROM audio_files").fetchone()[0] == 2
        assert integrity_check(snapshot) == "ok"
    finally:
        snapshot.close()

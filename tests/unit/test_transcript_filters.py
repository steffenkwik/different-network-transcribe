from __future__ import annotations

from pathlib import Path

import pytest

from app.database.connection import open_connection
from app.database.migrations import MigrationRunner
from app.database.repositories import TranscriptRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.unit]


def test_paged_list_supports_indexed_metadata_filters_and_safe_sort(tmp_path: Path) -> None:
    database = tmp_path / "Database" / "test.sqlite3"
    MigrationRunner(database, REPO_ROOT / "migrations", tmp_path / "Backups").migrate()
    connection = open_connection(database)
    try:
        root = int(connection.execute(
            "INSERT INTO source_roots(kind, original_path, normalized_path, created_at) VALUES ('audio','x','x','t')"
        ).lastrowid)
        for index, model in enumerate(("small", "medium")):
            audio = int(connection.execute(
                """INSERT INTO audio_files(stable_file_id, source_root_id, current_relative_path, basename,
                   normalized_basename, extension, size_bytes, first_discovered_at, last_seen_at, current_state,
                   created_at, updated_at) VALUES (?, ?, ?, ?, ?, '.opus', 1, 't', 't', 'completed_preferred', 't', 't')""",
                (f"stable-{index}", root, f"{index}.opus", f"{index}.opus", f"{index}.opus"),
            ).lastrowid)
            version = int(connection.execute(
                "INSERT INTO audio_source_versions(audio_file_id,size_bytes,sha256,discovered_at) VALUES (?,1,?,'t')",
                (audio, f"hash-{index}"),
            ).lastrowid)
            attempt = int(connection.execute(
                """INSERT INTO transcription_attempts(audio_file_id,source_version_id,model_name,engine_name,
                   engine_version,language,settings_json,compat_key,attempt_number,state,quality_status,created_at)
                   VALUES (?, ?, ?, 'fw','1','id','{}','key',1,'completed','Baik','t')""",
                (audio, version, model),
            ).lastrowid)
            connection.execute(
                "UPDATE audio_files SET current_source_version_id=?, preferred_transcript_id=? WHERE id=?",
                (version, attempt, audio),
            )
        page = TranscriptRepository(connection).list_page(limit=10, model_name="medium", sort="filename")
        assert page.total == 1
        assert page.rows[0]["model_name"] == "medium"
    finally:
        connection.close()

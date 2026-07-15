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

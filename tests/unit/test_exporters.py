"""Exporter tests use SQLite-only synthetic transcripts; source audio is never involved."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.database.connection import open_connection
from app.database.migrations import MigrationRunner
from app.exports.exporters import ExportService

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.unit]


def _seed(connection, timestamp: str | None, text: str, stable: str) -> None:
    root = connection.execute(
        "INSERT INTO source_roots(kind, original_path, normalized_path, created_at) VALUES ('audio','x','x-' || ?, 't')",
        (stable,),
    ).lastrowid
    audio = connection.execute(
        """INSERT INTO audio_files(stable_file_id,source_root_id,current_relative_path,basename,normalized_basename,extension,size_bytes,first_discovered_at,last_seen_at,current_state,created_at,updated_at) VALUES (?,?,?,?,?,?,1,'t','t','completed_preferred','t','t')""",
        (stable, root, f"{stable}.opus", f"{stable}.opus", f"{stable}.opus", ".opus"),
    ).lastrowid
    version = connection.execute(
        "INSERT INTO audio_source_versions(audio_file_id,size_bytes,sha256,discovered_at) VALUES (?,1,?,'t')",
        (audio, stable),
    ).lastrowid
    attempt = connection.execute(
        """INSERT INTO transcription_attempts(audio_file_id,source_version_id,model_name,engine_name,engine_version,language,settings_json,compat_key,attempt_number,state,started_at,completed_at,normalized_transcript,quality_status,created_at) VALUES (?,?, 'small','fw','1','id','{}','k',1,'completed','t','t',?,'Baik','t')""",
        (audio, version, text),
    ).lastrowid
    connection.execute(
        "UPDATE audio_files SET current_source_version_id=?,preferred_transcript_id=? WHERE id=?",
        (version, attempt, audio),
    )
    if timestamp:
        export = connection.execute(
            "INSERT INTO chat_exports(source_root_id,relative_path,sha256,first_discovered_at,parse_status) VALUES (?,?,?,'t','ok')",
            (root, f"{stable}.txt", stable),
        ).lastrowid
        ref = connection.execute(
            "INSERT INTO chat_voice_references(chat_export_id,line_number,sender_original,chat_original,whatsapp_message_at,header_hash) VALUES (?,1,'Synthetic Sender','Synthetic Chat',?,?)",
            (export, timestamp, stable),
        ).lastrowid
        connection.execute(
            "INSERT INTO metadata_matches(audio_file_id,chat_voice_reference_id,match_status,confidence,selected,created_at,updated_at) VALUES (?,?, 'exact_unique',1,1,'t','t')",
            (audio, ref),
        )


def test_exports_are_complete_deterministic_and_rebuildable(tmp_path: Path) -> None:
    database = tmp_path / "Database" / "test.sqlite3"
    MigrationRunner(database, REPO_ROOT / "migrations", tmp_path / "Backups").migrate()
    connection = open_connection(database)
    try:
        _seed(connection, "2026-07-15T20:31:00+07:00", "synthetic first", "one")
        _seed(connection, None, "synthetic unknown", "two")
        service = ExportService(connection, tmp_path / "Output")
        assert service.export_all(include_individual=True) == {"records": 2}
        daily = tmp_path / "Output" / "Markdown" / "Daily" / "2026" / "2026-07" / "2026-07-15.md"
        first = daily.read_bytes()
        service.export_all(include_individual=True)
        assert daily.read_bytes() == first
        assert "dnt-one" in daily.read_text(encoding="utf-8")
        assert (tmp_path / "Output" / "Markdown" / "Unknown-Date.md").exists()
        assert (
            tmp_path / "Output" / "Text" / "Daily" / "2026" / "2026-07" / "2026-07-15.txt"
        ).exists()
        assert (
            (tmp_path / "Output" / "CSV" / "semua-transkrip.csv")
            .read_bytes()
            .startswith(b"\xef\xbb\xbf")
        )
        lines = (
            (tmp_path / "Output" / "JSONL" / "semua-transkrip.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        assert len(lines) == 2 and all(json.loads(line) for line in lines)
        daily.unlink()
        attempts_before = connection.execute(
            "SELECT COUNT(*) FROM transcription_attempts"
        ).fetchone()[0]
        service.export_all()
        assert daily.exists()
        assert (
            connection.execute("SELECT COUNT(*) FROM transcription_attempts").fetchone()[0]
            == attempts_before
        )
    finally:
        connection.close()

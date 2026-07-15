from __future__ import annotations

from pathlib import Path

import pytest

from app.database.connection import open_connection
from app.database.migrations import MigrationRunner
from app.services.metadata_matching_service import MetadataMatchingService

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.unit]


def test_exact_filename_persists_selected_match_without_guessing(tmp_path: Path) -> None:
    database = tmp_path / "test.sqlite3"
    MigrationRunner(database, REPO_ROOT / "migrations", tmp_path / "backups").migrate()
    connection = open_connection(database)
    try:
        root = connection.execute("INSERT INTO source_roots(kind,original_path,normalized_path,created_at) VALUES ('audio','a','a','t')").lastrowid
        audio = connection.execute("INSERT INTO audio_files(stable_file_id,source_root_id,current_relative_path,basename,normalized_basename,extension,size_bytes,first_discovered_at,last_seen_at,current_state,created_at,updated_at) VALUES ('x',?,'x.opus','x.opus','x.opus','.opus',1,'t','t','discovered','t','t')", (root,)).lastrowid
        chat_root = connection.execute("INSERT INTO source_roots(kind,original_path,normalized_path,created_at) VALUES ('chat','c','c','t')").lastrowid
        export = connection.execute("INSERT INTO chat_exports(source_root_id,relative_path,sha256,first_discovered_at,parse_status) VALUES (?, 'c.txt','h','t','ok')", (chat_root,)).lastrowid
        reference = connection.execute("INSERT INTO chat_voice_references(chat_export_id,line_number,sender_original,referenced_filename,normalized_filename,parser_pattern,parser_confidence,header_hash) VALUES (?,1,'Synthetic Sender','x.opus','x.opus','dash',1,'h')", (export,)).lastrowid
        assert MetadataMatchingService(connection).run().selected == 1
        row = connection.execute("SELECT chat_voice_reference_id,selected,confidence FROM metadata_matches WHERE audio_file_id=?", (audio,)).fetchone()
        assert tuple(row) == (reference, 1, 1.0)
    finally:
        connection.close()

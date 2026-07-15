from __future__ import annotations

from pathlib import Path

import pytest

from app.database.connection import open_connection
from app.database.migrations import MigrationRunner
from app.services.chat_import_service import ChatImportService

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.unit]


def test_import_is_idempotent_and_stores_only_voice_reference_fields(tmp_path: Path) -> None:
    database = tmp_path / "data.sqlite3"
    MigrationRunner(database, REPO_ROOT / "migrations", tmp_path / "backups").migrate()
    folder = tmp_path / "chats"
    folder.mkdir()
    (folder / "Synthetic Chat.txt").write_text(
        "14/07/2026, 20.31 - Daniel: PTT-001.opus (file attached)\nchat body not stored\n",
        encoding="utf-8",
    )
    connection = open_connection(database)
    try:
        service = ChatImportService(connection)
        assert service.scan(folder).references == 1
        assert service.scan(folder).unchanged == 1
        row = connection.execute("SELECT sender_original,referenced_filename FROM chat_voice_references").fetchone()
        assert tuple(row) == ("Daniel", "PTT-001.opus")
    finally:
        connection.close()

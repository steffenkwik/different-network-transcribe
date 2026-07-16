"""Worker control stays process-based and queues durable commands only."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.database.connection import open_connection
from app.database.migrations import MigrationRunner
from app.database.worker_repository import WorkerRepository
from app.services.worker_control_service import WorkerControlService

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.unit]


def test_start_spawns_worker_role_without_importing_ui(tmp_path: Path) -> None:
    database = tmp_path / "Database" / "test.sqlite3"
    MigrationRunner(database, REPO_ROOT / "migrations", tmp_path / "Backups").migrate()
    service = WorkerControlService(database, tmp_path)
    with patch("app.services.worker_control_service.subprocess.Popen") as spawn:
        spawn.return_value.pid = 4321
        assert service.start() == 4321
    command = spawn.call_args.args[0]
    assert "--worker" in command
    assert "--data-dir" in command
    assert "--session" in command
    assert service.live_session_id() is not None
    with pytest.raises(RuntimeError, match="sudah berjalan"):
        service.start()


def test_pause_and_safe_stop_enqueue_commands_for_live_session(tmp_path: Path) -> None:
    database = tmp_path / "Database" / "test.sqlite3"
    MigrationRunner(database, REPO_ROOT / "migrations", tmp_path / "Backups").migrate()
    connection = open_connection(database)
    try:
        session = WorkerRepository(connection).acquire_lease("control", 1)
    finally:
        connection.close()
    service = WorkerControlService(database, tmp_path)
    service.pause()
    service.safe_stop()
    check = open_connection(database, read_only=True)
    try:
        commands = [
            row[0]
            for row in check.execute(
                "SELECT command FROM worker_commands WHERE session_id = ? ORDER BY id", (session,)
            )
        ]
    finally:
        check.close()
    assert commands == ["pause", "safe_stop"]


def test_live_session_reports_paused_state_and_resume_command(tmp_path: Path) -> None:
    database = tmp_path / "Database" / "test.sqlite3"
    MigrationRunner(database, REPO_ROOT / "migrations", tmp_path / "Backups").migrate()
    connection = open_connection(database)
    try:
        session = WorkerRepository(connection).acquire_lease("paused-control", 1)
        WorkerRepository(connection).heartbeat(session, "paused")
    finally:
        connection.close()
    service = WorkerControlService(database, tmp_path)
    assert service.live_session() == (session, "paused")
    service.resume()
    check = open_connection(database, read_only=True)
    try:
        assert check.execute(
            "SELECT command FROM worker_commands WHERE session_id = ?", (session,)
        ).fetchone()[0] == "resume"
    finally:
        check.close()


def test_retry_and_selected_reprocess_are_explicit_durable_commands(tmp_path: Path) -> None:
    database = tmp_path / "Database" / "test.sqlite3"
    MigrationRunner(database, REPO_ROOT / "migrations", tmp_path / "Backups").migrate()
    connection = open_connection(database)
    try:
        session = WorkerRepository(connection).acquire_lease("explicit", 1)
    finally:
        connection.close()
    service = WorkerControlService(database, tmp_path)
    service.retry_failed()
    service.reprocess_selected([12])
    check = open_connection(database, read_only=True)
    try:
        rows = check.execute(
            "SELECT command, payload_json FROM worker_commands WHERE session_id = ? ORDER BY id", (session,)
        ).fetchall()
        assert rows[0]["command"] == "retry_failed"
        assert rows[1]["command"] == "reprocess_selected"
        assert rows[1]["payload_json"] == '{"audio_file_ids": [12]}'
    finally:
        check.close()

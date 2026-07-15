"""Launch and control the separate local transcription worker process."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

from app.database.connection import open_connection
from app.database.worker_repository import LIVE_STATES, WorkerRepository, _is_live


class WorkerControlService:
    """The UI never transcribes directly; it only starts or commands a worker."""

    def __init__(self, database_file: Path, data_root: Path) -> None:
        self.database_file = database_file
        self.data_root = data_root

    def start(self) -> int:
        token = uuid.uuid4().hex
        connection = open_connection(self.database_file)
        try:
            WorkerRepository(connection).acquire_lease(token, None)
        finally:
            connection.close()
        command = self._worker_command(token)
        try:
            process = subprocess.Popen(command, close_fds=True)
        except OSError:
            connection = open_connection(self.database_file)
            try:
                session_id = self._session_id_for_token(connection, token)
                WorkerRepository(connection).stop(session_id, failed=True)
            finally:
                connection.close()
            raise
        return process.pid

    def pause(self) -> None:
        self._command_live("pause")

    def resume(self) -> None:
        self._command_live("resume")

    def safe_stop(self) -> None:
        self._command_live("safe_stop")

    def live_session_id(self) -> int | None:
        connection = open_connection(self.database_file, read_only=True)
        try:
            rows = connection.execute(
                "SELECT id, heartbeat_at, state FROM worker_sessions ORDER BY id DESC"
            ).fetchall()
        finally:
            connection.close()
        for row in rows:
            if row["state"] in LIVE_STATES and _is_live(str(row["heartbeat_at"])):
                return int(row["id"])
        return None

    def _command_live(self, command: str) -> None:
        connection = open_connection(self.database_file)
        try:
            session_id = self.live_session_id()
            if session_id is None:
                raise RuntimeError("Tidak ada proses transkripsi aktif.")
            WorkerRepository(connection).enqueue_command(session_id, command)
        finally:
            connection.close()

    def _worker_command(self, token: str) -> list[str]:
        if getattr(sys, "frozen", False):
            executable = sys.executable
            return [executable, "--worker", "--data-dir", str(self.data_root), "--session", token]
        return [
            sys.executable,
            "-m",
            "app.main",
            "--worker",
            "--data-dir",
            str(self.data_root),
            "--session",
            token,
        ]

    @staticmethod
    def _session_id_for_token(connection: sqlite3.Connection, token: str) -> int:
        row = connection.execute(
            "SELECT id FROM worker_sessions WHERE instance_token = ?", (token,)
        ).fetchone()
        if row is None:
            raise RuntimeError("Sesi worker tidak ditemukan.")
        return int(row["id"])

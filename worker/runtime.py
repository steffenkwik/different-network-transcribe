"""Separate worker loop. It is Qt-free and keeps one local model instance loaded."""

from __future__ import annotations

import os
from pathlib import Path

from app.database.connection import open_connection
from app.database.worker_repository import WorkerRepository
from app.services.queue_service import QueueService
from app.transcription.engine import TranscriptionEngine


class WorkerLoop:
    def __init__(
        self, database_file: Path, instance_token: str, engine: TranscriptionEngine
    ) -> None:
        self.connection = open_connection(database_file)
        self.repository = WorkerRepository(self.connection)
        self.queue_service = QueueService(self.connection)
        self.instance_token = instance_token
        self.engine = engine
        self.session_id: int | None = None
        self.loaded = False
        self.paused = False
        self.stopped = False

    def start(self) -> int:
        self.session_id = self.repository.acquire_lease(self.instance_token, os.getpid())
        # This is the sole bridge from discovered records to worker-claimable
        # rows. It records completed sources as skipped instead of re-inferencing
        # them when a session is started again.
        self.queue_service.prepare()
        self.engine.load()
        self.loaded = True
        self.repository.heartbeat(self.session_id, "running")
        return self.session_id

    def run_one(self) -> bool:
        if self.session_id is None:
            raise RuntimeError("Worker belum dimulai.")
        command = self.repository.next_command(self.session_id)
        if command is not None and command["command"] in {"safe_stop", "shutdown"}:
            self.repository.complete_command(int(command["id"]))
            self.repository.stop(self.session_id)
            self.stopped = True
            return False
        if command is not None and command["command"] == "pause":
            self.paused = True
            self.repository.heartbeat(self.session_id, "paused")
            self.repository.complete_command(int(command["id"]))
            return False
        if command is not None and command["command"] == "resume":
            self.paused = False
            self.repository.heartbeat(self.session_id, "running")
            self.repository.complete_command(int(command["id"]))
            return False
        if self.paused:
            self.repository.heartbeat(self.session_id, "paused")
            return False
        record = self.repository.claim_next(self.session_id)
        if record is None:
            self.repository.heartbeat(self.session_id, "idle")
            return False
        try:
            result = self.engine.transcribe(
                Path(str(record["source_root_path"])) / str(record["current_relative_path"])
            )
            self.repository.complete_attempt(int(record["attempt_id"]), int(record["id"]), result)
        except Exception as exc:
            self.repository.fail_attempt(
                int(record["attempt_id"]), int(record["id"]), type(exc).__name__
            )
        self.repository.heartbeat(self.session_id, "running")
        return True

    def close(self) -> None:
        if self.session_id is not None:
            self.repository.stop(self.session_id)
        self.connection.close()

"""Separate worker loop. It is Qt-free and keeps one local model instance loaded."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from app.database.connection import open_connection
from app.database.worker_repository import WorkerRepository
from app.services.queue_service import QueueService
from app.transcription.engine import TranscriptionEngine


class WorkerLoop:
    def __init__(
        self, database_file: Path, instance_token: str, engine: TranscriptionEngine, status_file: Path | None = None, active_root: Path | None = None
    ) -> None:
        self.connection = open_connection(database_file)
        self.repository = WorkerRepository(self.connection)
        self.queue_service = QueueService(self.connection, active_root)
        self.instance_token = instance_token
        self.engine = engine
        self.status_file = status_file
        self.active_root = None if active_root is None else str(active_root.resolve())
        self.session_id: int | None = None
        self.loaded = False
        self.paused = False
        self.stopped = False

    def start(self) -> int:
        self.session_id = self.repository.attach_lease(self.instance_token, os.getpid())
        # This is the sole bridge from discovered records to worker-claimable
        # rows. It records completed sources as skipped instead of re-inferencing
        # them when a session is started again.
        self.queue_service.prepare()
        self.engine.load()
        self.loaded = True
        self.repository.heartbeat(self.session_id, "running")
        self._write_status("running")
        return self.session_id

    def run_one(self) -> bool:
        if self.session_id is None:
            raise RuntimeError("Worker belum dimulai.")
        command = self.repository.next_command(self.session_id)
        if command is not None and command["command"] in {"safe_stop", "shutdown"}:
            self.repository.complete_command(int(command["id"]))
            self.repository.stop(self.session_id)
            self.stopped = True
            self._write_status("stopped")
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
        if command is not None and command["command"] == "reprocess_selected":
            payload = json.loads(str(command["payload_json"] or "{}"))
            ids = payload.get("audio_file_ids", [])
            if not isinstance(ids, list) or not all(isinstance(item, int) for item in ids):
                self.repository.complete_command(int(command["id"]), "invalid_payload")
                return False
            requeued = self.repository.requeue_selected(ids)
            self.repository.complete_command(int(command["id"]), f"requeued:{requeued}")
        if self.paused:
            self.repository.heartbeat(self.session_id, "paused")
            return False
        record = self.repository.claim_next(self.session_id, self.active_root)
        if record is None:
            self.repository.heartbeat(self.session_id, "idle")
            self._write_status("idle")
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
        self._write_status("running")
        return True

    def close(self) -> None:
        if self.session_id is not None:
            self.repository.stop(self.session_id)
        self.connection.close()

    def _write_status(self, state: str) -> None:
        if self.status_file is None:
            return
        rows = self.connection.execute(
            """SELECT a.current_state, COUNT(*) AS total
               FROM audio_files a
               JOIN source_roots s ON s.id = a.source_root_id
               WHERE (? IS NULL OR s.original_path = ?)
               GROUP BY a.current_state""",
            (self.active_root, self.active_root),
        ).fetchall()
        counts = {str(row["current_state"]): int(row["total"]) for row in rows}
        payload = {
            "schema": 1, "instance_token": self.instance_token, "state": state,
            "updated_at": datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
            "counts": {"queued": counts.get("queued", 0), "completed": counts.get("completed_preferred", 0),
                       "failed": counts.get("failed", 0)},
        }
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.status_file.with_suffix(".tmp")
        temp.write_text(json.dumps(payload), encoding="utf-8")
        temp.replace(self.status_file)

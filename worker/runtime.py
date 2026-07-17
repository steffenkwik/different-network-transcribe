"""Separate worker loop. It is Qt-free and keeps one local model instance loaded."""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from app.database.connection import open_connection
from app.database.worker_repository import WorkerRepository
from app.services.queue_service import QueueService
from app.transcription.engine import TranscriptionEngine
from app.transcription.quality import assess


class WorkerLoop:
    def __init__(
        self,
        database_file: Path,
        instance_token: str,
        engine: TranscriptionEngine,
        status_file: Path | None = None,
        active_root: Path | None = None,
        active_roots: list[Path] | None = None,
        heartbeat_interval_seconds: float = 2.0,
        model_name: str = "small",
        model_hash: str | None = None,
        language: str = "id",
        attempt_settings: dict[str, object] | None = None,
    ) -> None:
        self.database_file = database_file
        self.connection = open_connection(database_file)
        self.repository = WorkerRepository(self.connection)
        roots = active_roots if active_roots is not None else ([] if active_root is None else [active_root])
        self.active_roots = sorted({str(root.resolve()) for root in roots}) or None
        self.queue_service = QueueService(self.connection, active_roots=roots)
        self.instance_token = instance_token
        self.engine = engine
        self.status_file = status_file
        self.active_root = None if active_root is None else str(active_root.resolve())
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.model_name = model_name
        self.model_hash = model_hash
        self.language = language
        self.attempt_settings = attempt_settings
        self.session_id: int | None = None
        self.loaded = False
        self.paused = False
        self.stopped = False
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

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
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="dnt-worker-heartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()
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
            self._write_status("paused")
            return False
        if command is not None and command["command"] == "resume":
            self.paused = False
            self.repository.heartbeat(self.session_id, "running")
            self.repository.complete_command(int(command["id"]))
            self._write_status("running")
            return False
        if command is not None and command["command"] == "reprocess_selected":
            payload = json.loads(str(command["payload_json"] or "{}"))
            ids = payload.get("audio_file_ids", [])
            if not isinstance(ids, list) or not all(isinstance(item, int) for item in ids):
                self.repository.complete_command(int(command["id"]), "invalid_payload")
                return False
            requeued = self.repository.requeue_selected(ids)
            self.repository.complete_command(int(command["id"]), f"requeued:{requeued}")
        if command is not None and command["command"] == "retry_failed":
            requeued = self.repository.requeue_failed(self.active_root, active_roots=self.active_roots)
            self.repository.complete_command(int(command["id"]), f"requeued_failed:{requeued}")
        if self.paused:
            self.repository.heartbeat(self.session_id, "paused")
            return False
        record = self.repository.claim_next(
            self.session_id,
            self.active_root,
            active_roots=self.active_roots,
            model_name=self.model_name,
            model_hash=self.model_hash,
            language=self.language,
            settings=self.attempt_settings,
        )
        if record is None:
            self.repository.heartbeat(self.session_id, "idle")
            self._write_status("idle")
            return False
        try:
            result = self.engine.transcribe(
                Path(str(record["source_root_path"])) / str(record["current_relative_path"])
            )
            self.repository.complete_attempt(
                int(record["attempt_id"]),
                int(record["id"]),
                result,
                assess(result, record["duration_seconds"]),
            )
        except Exception as exc:
            self.repository.fail_attempt(
                int(record["attempt_id"]), int(record["id"]), type(exc).__name__
            )
        self.repository.heartbeat(self.session_id, "running")
        self._write_status("running")
        return True

    def close(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=self.heartbeat_interval_seconds + 1.0)
        if self.session_id is not None:
            self.repository.stop(self.session_id)
        self.connection.close()

    def _heartbeat_loop(self) -> None:
        """Keep the lease fresh during a long local inference without sharing SQLite connections."""
        while not self._heartbeat_stop.wait(self.heartbeat_interval_seconds):
            if self.session_id is None or self.stopped:
                return
            connection = open_connection(self.database_file)
            try:
                WorkerRepository(connection).heartbeat(
                    self.session_id, "paused" if self.paused else "running"
                )
            finally:
                connection.close()

    def _write_status(self, state: str) -> None:
        if self.status_file is None:
            return
        root_where, root_parameters = _root_filter(self.active_roots, "s.original_path")
        rows = self.connection.execute(
            """SELECT a.current_state, COUNT(*) AS total
               FROM audio_files a
               JOIN source_roots s ON s.id = a.source_root_id
               WHERE """ + root_where + " GROUP BY a.current_state",
            root_parameters,
        ).fetchall()
        counts = {str(row["current_state"]): int(row["total"]) for row in rows}
        payload = {
            "schema": 1, "instance_token": self.instance_token, "state": state,
            "updated_at": datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
            "model": self.model_name,
            "model_loaded": self.loaded,
            "model_load_count": 1 if self.loaded else 0,
            "counts": {"queued": counts.get("queued", 0), "completed": counts.get("completed_preferred", 0),
                       "failed": counts.get("failed", 0)},
        }
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.status_file.with_suffix(".tmp")
        temp.write_text(json.dumps(payload), encoding="utf-8")
        temp.replace(self.status_file)


def _root_filter(roots: list[str] | None, column: str) -> tuple[str, list[str]]:
    if roots is None:
        return "1 = 1", []
    return f"{column} IN ({','.join('?' for _ in roots)})", roots

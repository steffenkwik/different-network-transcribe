"""Separate worker loop. It is Qt-free and keeps one local model instance loaded."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from app.database.connection import open_connection
from app.database.worker_repository import WorkerRepository
from app.services.queue_service import QueueService
from app.services.worker_status import STATUS_SCHEMA, SessionProgress
from app.transcription.engine import TranscriptionEngine
from app.transcription.quality import assess


class WorkerStep(Enum):
    """The outcome of one loop iteration.

    A bool return could not distinguish "nothing to do right now" from "stop the
    process", which previously made a resume command terminate the worker.
    """

    PROCESSED = "processed"
    COMMAND_HANDLED = "command_handled"
    IDLE = "idle"
    PAUSED = "paused"
    STOPPED = "stopped"


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
        self.progress = SessionProgress()
        self._prepare_progress: tuple[int, int] = (0, 0)
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

    def start(self) -> int:
        self.session_id = self.repository.attach_lease(self.instance_token, os.getpid())
        self._write_status("preparing")
        # This is the sole bridge from discovered records to worker-claimable
        # rows. It records completed sources as skipped instead of re-inferencing
        # them when a session is started again.
        preparation = self.queue_service.prepare(progress=self._report_preparation)
        # The session total is fixed here so the progress bar has a stable
        # denominator; work added later starts a new session.
        self.progress = SessionProgress(total=preparation.queued)
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

    def run_one(self) -> WorkerStep:
        """Advance the loop by exactly one action and report what happened."""
        if self.session_id is None:
            raise RuntimeError("Worker belum dimulai.")
        command = self.repository.next_command(self.session_id)
        if command is not None:
            return self._handle_command(command)
        if self.paused:
            self.repository.heartbeat(self.session_id, "paused")
            return WorkerStep.PAUSED
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
            return WorkerStep.IDLE
        self.progress.start_file(str(record["basename"]))
        self._write_status("running")
        started = time.monotonic()
        failed = False
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
            failed = True
            self.repository.fail_attempt(
                int(record["attempt_id"]), int(record["id"]), type(exc).__name__
            )
        self.progress.record_finished(time.monotonic() - started, failed=failed)
        self.repository.heartbeat(self.session_id, "running")
        self._write_status("running")
        return WorkerStep.PROCESSED

    def _handle_command(self, command: sqlite3.Row) -> WorkerStep:
        """Apply one queued command. Only an explicit stop ends the process."""
        assert self.session_id is not None
        name = str(command["command"])
        command_id = int(command["id"])
        if name in {"safe_stop", "shutdown"}:
            self.repository.complete_command(command_id)
            self.repository.stop(self.session_id)
            self.stopped = True
            self._write_status("stopped")
            return WorkerStep.STOPPED
        if name == "pause":
            self.paused = True
            self.repository.heartbeat(self.session_id, "paused")
            self.repository.complete_command(command_id)
            self._write_status("paused")
            return WorkerStep.PAUSED
        if name == "resume":
            # The loop must stay alive here: the next iteration claims work again.
            self.paused = False
            self.repository.heartbeat(self.session_id, "running")
            self.repository.complete_command(command_id)
            self._write_status("running")
            return WorkerStep.COMMAND_HANDLED
        if name == "reprocess_selected":
            payload = json.loads(str(command["payload_json"] or "{}"))
            ids = payload.get("audio_file_ids", [])
            if not isinstance(ids, list) or not all(isinstance(item, int) for item in ids):
                self.repository.complete_command(command_id, "invalid_payload")
                return WorkerStep.COMMAND_HANDLED
            requeued = self.repository.requeue_selected(ids)
            # Work added mid-session must widen the denominator, otherwise the
            # bar would report more than 100% complete.
            self.progress.total += requeued
            self.repository.complete_command(command_id, f"requeued:{requeued}")
            self._write_status("running" if not self.paused else "paused")
            return WorkerStep.COMMAND_HANDLED
        if name == "retry_failed":
            requeued = self.repository.requeue_failed(
                self.active_root, active_roots=self.active_roots
            )
            self.progress.total += requeued
            self.repository.complete_command(command_id, f"requeued_failed:{requeued}")
            self._write_status("running" if not self.paused else "paused")
            return WorkerStep.COMMAND_HANDLED
        self.repository.complete_command(command_id, "unknown_command")
        return WorkerStep.COMMAND_HANDLED

    def finish(self) -> None:
        """Report an exhausted queue so the UI can distinguish it from a crash."""
        self._write_status("finished")

    def _report_preparation(self, done: int, total: int) -> None:
        """Publish preparation progress so a large archive never looks frozen."""
        if self.status_file is None:
            return
        self._prepare_progress = (done, total)
        self._write_status("preparing", with_counts=False)

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

    def _write_status(self, state: str, *, with_counts: bool = True) -> None:
        if self.status_file is None:
            return
        counts: dict[str, int] = {}
        if with_counts:
            # Skipped while preparing: that runs inside one write transaction and
            # is called every 50 rows, where an aggregate per call would cost more
            # than the work it reports on.
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
            "schema": STATUS_SCHEMA,
            "instance_token": self.instance_token,
            "state": state,
            "updated_at": datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
            "model": self.model_name,
            "model_loaded": self.loaded,
            "model_load_count": 1 if self.loaded else 0,
            # Progress belongs to this session; `counts` stays all-time and is
            # diagnostic only, because mixing the two is what made the bar lie.
            "session": self.progress.as_payload(),
            "prepare": {
                "done": self._prepare_progress[0],
                "total": self._prepare_progress[1],
            },
            "counts": {
                "queued": counts.get("queued", 0),
                "completed": counts.get("completed_preferred", 0),
                "failed": counts.get("failed", 0),
            },
        }
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.status_file.with_suffix(".tmp")
        temp.write_text(json.dumps(payload), encoding="utf-8")
        temp.replace(self.status_file)


def _root_filter(roots: list[str] | None, column: str) -> tuple[str, list[str]]:
    if roots is None:
        return "1 = 1", []
    return f"{column} IN ({','.join('?' for _ in roots)})", roots

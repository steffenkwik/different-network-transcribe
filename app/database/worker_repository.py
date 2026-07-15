"""Durable worker lease, command, attempt and crash-recovery persistence."""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta

from app.database.connection import transaction
from app.database.repositories import now
from app.transcription.engine import EngineResult

LIVE_STATES = {"idle", "starting", "running", "pausing", "paused", "stopping"}


def _is_live(heartbeat_at: str, *, timeout_seconds: int = 10) -> bool:
    from datetime import datetime

    return datetime.fromisoformat(heartbeat_at) >= datetime.fromisoformat(now()) - timedelta(
        seconds=timeout_seconds
    )


class WorkerRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def acquire_lease(self, instance_token: str, pid: int | None) -> int:
        with transaction(self.connection, immediate=True):
            rows = self.connection.execute(
                "SELECT id, heartbeat_at, state FROM worker_sessions WHERE state NOT IN ('stopped', 'failed')"
            ).fetchall()
            if any(
                row["state"] in LIVE_STATES and _is_live(str(row["heartbeat_at"])) for row in rows
            ):
                raise RuntimeError("Proses transkripsi sudah berjalan.")
            cursor = self.connection.execute(
                """INSERT INTO worker_sessions(instance_token, pid, started_at, heartbeat_at, state)
                   VALUES (?, ?, ?, ?, 'starting')""",
                (instance_token, pid, now(), now()),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("Sesi worker tidak dapat dibuat.")
            return cursor.lastrowid

    def attach_lease(self, instance_token: str, pid: int | None) -> int:
        """Attach a spawned worker to the lease its UI parent created.

        Direct test/CLI use remains supported by falling back to lease acquisition.
        """
        with transaction(self.connection, immediate=True):
            row = self.connection.execute(
                "SELECT id, state FROM worker_sessions WHERE instance_token = ?", (instance_token,)
            ).fetchone()
            if row is not None:
                if row["state"] not in {"starting", "idle"}:
                    raise RuntimeError("Sesi worker tidak dapat dilanjutkan.")
                self.connection.execute(
                    "UPDATE worker_sessions SET pid = ?, heartbeat_at = ?, state = 'starting' WHERE id = ?",
                    (pid, now(), row["id"]),
                )
                return int(row["id"])
        return self.acquire_lease(instance_token, pid)

    def heartbeat(self, session_id: int, state: str) -> None:
        self.connection.execute(
            "UPDATE worker_sessions SET heartbeat_at = ?, state = ? WHERE id = ?",
            (now(), state, session_id),
        )

    def enqueue_command(
        self, session_id: int, command: str, payload: dict[str, object] | None = None
    ) -> int:
        cursor = self.connection.execute(
            "INSERT INTO worker_commands(session_id, command, payload_json, issued_at) VALUES (?, ?, ?, ?)",
            (session_id, command, None if payload is None else json.dumps(payload), now()),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Perintah worker tidak dapat dibuat.")
        return cursor.lastrowid

    def next_command(self, session_id: int) -> sqlite3.Row | None:
        row = self.connection.execute(
            """SELECT * FROM worker_commands WHERE session_id = ? AND acknowledged_at IS NULL
               ORDER BY id LIMIT 1""",
            (session_id,),
        ).fetchone()
        if row is not None:
            self.connection.execute(
                "UPDATE worker_commands SET acknowledged_at = ? WHERE id = ?", (now(), row["id"])
            )
        return row

    def complete_command(self, command_id: int, result: str = "ok") -> None:
        self.connection.execute(
            "UPDATE worker_commands SET completed_at = ?, result = ? WHERE id = ?",
            (now(), result, command_id),
        )

    def requeue_selected(self, audio_file_ids: list[int]) -> int:
        """Honor an explicit, narrow reprocess request without deleting history."""
        selected = sorted(set(audio_file_ids))
        if not selected:
            return 0
        placeholders = ",".join("?" for _ in selected)
        with transaction(self.connection, immediate=True):
            rows = self.connection.execute(
                f"""SELECT id FROM audio_files WHERE id IN ({placeholders})
                       AND current_source_version_id IS NOT NULL AND readable = 1 AND zero_byte = 0""",
                selected,
            ).fetchall()
            for row in rows:
                audio_file_id = int(row["id"])
                self.connection.execute(
                    "UPDATE audio_files SET current_state = 'queued', updated_at = ? WHERE id = ?",
                    (now(), audio_file_id),
                )
                self.connection.execute(
                    """INSERT INTO processing_events(audio_file_id, event_type, event_at, details_json)
                       VALUES (?, 'explicit_reprocess_requested', ?, '{}')""",
                    (audio_file_id, now()),
                )
        return len(rows)

    def claim_next(self, session_id: int) -> sqlite3.Row | None:
        with transaction(self.connection, immediate=True):
            audio = self.connection.execute(
                """SELECT a.*, v.id AS source_version_id, s.original_path AS source_root_path FROM audio_files a
                   JOIN audio_source_versions v ON v.id = a.current_source_version_id
                   JOIN source_roots s ON s.id = a.source_root_id
                   WHERE a.current_state = 'queued' AND a.readable = 1 AND a.zero_byte = 0
                   ORDER BY a.id LIMIT 1"""
            ).fetchone()
            if audio is None:
                return None
            attempt_number = int(
                self.connection.execute(
                    "SELECT COALESCE(MAX(attempt_number), 0) + 1 FROM transcription_attempts WHERE audio_file_id = ?",
                    (audio["id"],),
                ).fetchone()[0]
            )
            cursor = self.connection.execute(
                """INSERT INTO transcription_attempts(
                    audio_file_id, source_version_id, worker_session_id, model_name, model_hash,
                    engine_name, engine_version, language, settings_json, compat_key,
                    attempt_number, state, started_at, created_at)
                   VALUES (?, ?, ?, 'small', NULL, 'faster-whisper', 'local', 'id', '{}', 'pending', ?, 'processing', ?, ?)""",
                (audio["id"], audio["source_version_id"], session_id, attempt_number, now(), now()),
            )
            self.connection.execute(
                "UPDATE audio_files SET current_state = 'processing', updated_at = ? WHERE id = ?",
                (now(), audio["id"]),
            )
            return self.connection.execute(
                """SELECT a.*, s.original_path AS source_root_path, ? AS attempt_id
                   FROM audio_files a JOIN source_roots s ON s.id = a.source_root_id WHERE a.id = ?""",
                (cursor.lastrowid, audio["id"]),
            ).fetchone()

    def complete_attempt(self, attempt_id: int, audio_file_id: int, result: EngineResult) -> None:
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                """UPDATE transcription_attempts SET state = 'completed', completed_at = ?, raw_transcript = ?,
                   normalized_transcript = ?, segment_json = ?, detected_language = ?, language_probability = ?,
                   quality_status = 'Baik', quality_score = 1.0 WHERE id = ?""",
                (
                    now(),
                    result.raw_transcript,
                    result.normalized_transcript,
                    result.segment_json,
                    result.detected_language,
                    result.language_probability,
                    attempt_id,
                ),
            )
            self.connection.execute(
                """UPDATE audio_files SET current_state = 'completed_preferred', preferred_transcript_id = ?,
                   updated_at = ? WHERE id = ?""",
                (attempt_id, now(), audio_file_id),
            )

    def fail_attempt(self, attempt_id: int, audio_file_id: int, error_type: str) -> None:
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                """UPDATE transcription_attempts SET state = 'failed', completed_at = ?, error_type = ?,
                   safe_error_message = 'File tidak dapat dibaca. File dilewati dan proses dilanjutkan.' WHERE id = ?""",
                (now(), error_type, attempt_id),
            )
            self.connection.execute(
                "UPDATE audio_files SET current_state = 'failed', updated_at = ? WHERE id = ?",
                (now(), audio_file_id),
            )

    def stop(self, session_id: int, *, failed: bool = False) -> None:
        state = "failed" if failed else "stopped"
        self.connection.execute(
            "UPDATE worker_sessions SET state = ?, stopped_at = ? WHERE id = ?",
            (state, now(), session_id),
        )

    def recover_stale_sessions(self) -> int:
        recovered = 0
        with transaction(self.connection, immediate=True):
            sessions = self.connection.execute(
                "SELECT id, heartbeat_at, state FROM worker_sessions WHERE state NOT IN ('stopped', 'failed')"
            ).fetchall()
            for session in sessions:
                if _is_live(str(session["heartbeat_at"])):
                    continue
                self.connection.execute(
                    "UPDATE worker_sessions SET state = 'failed', stopped_at = ? WHERE id = ?",
                    (now(), session["id"]),
                )
                attempts = self.connection.execute(
                    "SELECT id, audio_file_id FROM transcription_attempts WHERE worker_session_id = ? AND state = 'processing'",
                    (session["id"],),
                ).fetchall()
                for attempt in attempts:
                    self.connection.execute(
                        "UPDATE transcription_attempts SET state = 'interrupted', completed_at = ? WHERE id = ?",
                        (now(), attempt["id"]),
                    )
                    self.connection.execute(
                        "UPDATE audio_files SET current_state = 'queued', updated_at = ? WHERE id = ?",
                        (now(), attempt["audio_file_id"]),
                    )
                    recovered += 1
        return recovered

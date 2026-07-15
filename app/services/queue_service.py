"""Prepare a transcription queue without ever invalidating completed work by settings drift."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.database.connection import transaction
from app.database.repositories import now
from app.services.discovery_service import sha256_file
from app.services.reuse_policy import ReuseState, next_action


@dataclass(frozen=True)
class QueuePreparation:
    queued: int = 0
    skipped_complete: int = 0
    missing_source: int = 0
    source_changed: int = 0


class QueueService:
    """The only service which changes discovery records into worker-claimable rows.

    It deliberately bases reuse solely on bytes, stored transcript integrity, and an
    explicit request. Model, engine, export, or UI configuration are absent here.
    """

    def __init__(self, connection: sqlite3.Connection, active_root: Path | None = None) -> None:
        self.connection = connection
        self.active_root = None if active_root is None else str(active_root.resolve())

    def prepare(self) -> QueuePreparation:
        rows = self.connection.execute(
            """
            SELECT a.id, a.current_state, a.current_relative_path, a.current_source_version_id, s.original_path,
                   v.sha256 AS stored_sha256,
                   t.id AS preferred_attempt_id, t.state AS preferred_state,
                   t.source_version_id AS preferred_source_version_id,
                   t.raw_transcript
            FROM audio_files a
            JOIN source_roots s ON s.id = a.source_root_id
            LEFT JOIN audio_source_versions v ON v.id = a.current_source_version_id
            LEFT JOIN transcription_attempts t ON t.id = a.preferred_transcript_id
            WHERE a.readable = 1 AND a.zero_byte = 0
              AND (? IS NULL OR s.original_path = ?)
            ORDER BY a.id
            """,
            (self.active_root, self.active_root),
        ).fetchall()
        summary = QueuePreparation()
        for row in rows:
            source = Path(str(row["original_path"])) / str(row["current_relative_path"])
            exists = source.is_file()
            observed = sha256_file(source) if exists else None
            has_completed = (
                row["preferred_attempt_id"] is not None
                and row["preferred_state"] == "completed"
                and row["preferred_source_version_id"] == row["current_source_version_id"]
            )
            valid = has_completed and row["raw_transcript"] is not None
            state = ReuseState(
                source_exists=exists,
                on_disk_sha256=observed,
                stored_sha256=None if row["stored_sha256"] is None else str(row["stored_sha256"]),
                completed_transcript_exists=has_completed,
                preferred_transcript_valid=valid,
                explicit_reprocess_pending=False,
            )
            action = next_action(state)
            if action == "skipped_complete":
                self._event(int(row["id"]), action)
                summary = QueuePreparation(
                    queued=summary.queued,
                    skipped_complete=summary.skipped_complete + 1,
                    missing_source=summary.missing_source,
                    source_changed=summary.source_changed,
                )
            elif action == "missing_source":
                self._set_state(int(row["id"]), action)
                summary = QueuePreparation(
                    queued=summary.queued,
                    skipped_complete=summary.skipped_complete,
                    missing_source=summary.missing_source + 1,
                    source_changed=summary.source_changed,
                )
            elif action == "stale_source_changed":
                self._set_state(int(row["id"]), action)
                summary = QueuePreparation(
                    queued=summary.queued,
                    skipped_complete=summary.skipped_complete,
                    missing_source=summary.missing_source,
                    source_changed=summary.source_changed + 1,
                )
            else:
                self._set_state(int(row["id"]), "queued")
                summary = QueuePreparation(
                    queued=summary.queued + 1,
                    skipped_complete=summary.skipped_complete,
                    missing_source=summary.missing_source,
                    source_changed=summary.source_changed,
                )
        return summary

    def _set_state(self, audio_file_id: int, state: str) -> None:
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                "UPDATE audio_files SET current_state = ?, updated_at = ? WHERE id = ?",
                (state, now(), audio_file_id),
            )
            self._event(audio_file_id, state)

    def _event(self, audio_file_id: int, event_type: str) -> None:
        self.connection.execute(
            """INSERT INTO processing_events(audio_file_id, event_type, event_at, details_json)
               VALUES (?, ?, ?, ?)""",
            (audio_file_id, event_type, now(), json.dumps({"source": "queue_prepare"})),
        )

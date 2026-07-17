"""Prepare a transcription queue without ever invalidating completed work by settings drift."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.database.connection import transaction
from app.database.repositories import now
from app.services.discovery_service import iso_local, sha256_file
from app.services.reuse_policy import ReuseState, next_action

#: How often a long preparation reports progress. Frequent enough to look alive,
#: rare enough not to cost more than the work it measures.
PROGRESS_EVERY = 50

ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class QueuePreparation:
    queued: int = 0
    skipped_complete: int = 0
    missing_source: int = 0
    source_changed: int = 0
    rehashed: int = 0


class QueueService:
    """The only service which changes discovery records into worker-claimable rows.

    It deliberately bases reuse solely on bytes, stored transcript integrity, and an
    explicit request. Model, engine, export, or UI configuration are absent here.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        active_root: Path | None = None,
        active_roots: list[Path] | None = None,
    ) -> None:
        self.connection = connection
        roots = active_roots if active_roots is not None else ([] if active_root is None else [active_root])
        self.active_roots = sorted({str(root.resolve()) for root in roots}) or None

    def prepare(self, progress: ProgressCallback | None = None) -> QueuePreparation:
        root_where, root_parameters = self._root_filter("s.original_path")
        rows = self.connection.execute(
            """
            SELECT a.id, a.current_state, a.transcription_enabled, a.current_relative_path, a.current_source_version_id, s.original_path,
                   v.sha256 AS stored_sha256,
                   v.size_bytes AS stored_size_bytes,
                   v.modified_at AS stored_modified_at,
                   t.id AS preferred_attempt_id, t.state AS preferred_state,
                   t.source_version_id AS preferred_source_version_id,
                   t.raw_transcript
            FROM audio_files a
            JOIN source_roots s ON s.id = a.source_root_id
            LEFT JOIN audio_source_versions v ON v.id = a.current_source_version_id
            LEFT JOIN transcription_attempts t ON t.id = a.preferred_transcript_id
            WHERE a.readable = 1 AND a.zero_byte = 0
              AND """ + root_where + " ORDER BY a.id",
            root_parameters,
        ).fetchall()
        total = len(rows)
        queued = skipped = missing = changed = rehashed = 0
        # One transaction for the whole preparation: an archive of thousands
        # would otherwise pay for thousands of separate commits before the first
        # file is ever transcribed.
        with transaction(self.connection, immediate=True):
            for index, row in enumerate(rows):
                if progress is not None and index % PROGRESS_EVERY == 0:
                    progress(index, total)
                # A user exclusion is an explicit, persistent decision.  It is
                # checked before every other queue rule so a later app restart or
                # configuration edit cannot silently put the file back in queue.
                if not bool(row["transcription_enabled"]):
                    if row["current_state"] not in {"completed_preferred", "verified", "excluded"}:
                        self._set_state(int(row["id"]), "excluded")
                    continue
                # A failed/no-speech attempt is not a blank record.  It must never
                # silently become eligible again on an ordinary restart; retry is a
                # distinct user command and preserves the previous attempt.
                if row["current_state"] in {"failed", "no_speech"}:
                    continue
                source = Path(str(row["original_path"])) / str(row["current_relative_path"])
                observed, hashed = self._observed_sha256(source, row)
                rehashed += int(hashed)
                has_completed = (
                    row["preferred_attempt_id"] is not None
                    and row["preferred_state"] == "completed"
                    and row["preferred_source_version_id"] == row["current_source_version_id"]
                )
                valid = has_completed and row["raw_transcript"] is not None
                state = ReuseState(
                    source_exists=observed is not None or source.is_file(),
                    on_disk_sha256=observed,
                    stored_sha256=None if row["stored_sha256"] is None else str(row["stored_sha256"]),
                    completed_transcript_exists=has_completed,
                    preferred_transcript_valid=valid,
                    explicit_reprocess_pending=False,
                )
                action = next_action(state)
                if action == "skipped_complete":
                    self._event(int(row["id"]), action)
                    skipped += 1
                elif action == "missing_source":
                    self._set_state(int(row["id"]), action)
                    missing += 1
                elif action == "stale_source_changed":
                    self._set_state(int(row["id"]), action)
                    changed += 1
                else:
                    self._set_state(int(row["id"]), "queued")
                    queued += 1
        if progress is not None:
            progress(total, total)
        return QueuePreparation(
            queued=queued,
            skipped_complete=skipped,
            missing_source=missing,
            source_changed=changed,
            rehashed=rehashed,
        )

    def _observed_sha256(self, source: Path, row: sqlite3.Row) -> tuple[str | None, bool]:
        """Identify the file on disk, re-hashing only when it may have changed.

        Identity stays SHA-256: this only avoids recomputing a hash whose inputs
        demonstrably have not moved. Re-reading every byte of a 13,000-file
        archive on each start made the app look frozen for many minutes before
        the first voice note was transcribed.

        Returns the hash and whether it had to be recomputed.
        """
        try:
            stat = source.stat()
        except OSError:
            return None, False
        stored_hash = row["stored_sha256"]
        unchanged = (
            stored_hash is not None
            and row["stored_size_bytes"] is not None
            and int(row["stored_size_bytes"]) == stat.st_size
            and row["stored_modified_at"] is not None
            and str(row["stored_modified_at"]) == iso_local(stat.st_mtime)
        )
        if unchanged:
            return str(stored_hash), False
        try:
            return sha256_file(source), True
        except OSError:
            return None, False

    def _set_state(self, audio_file_id: int, state: str) -> None:
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

    def _root_filter(self, column: str) -> tuple[str, list[str]]:
        if self.active_roots is None:
            return "1 = 1", []
        return f"{column} IN ({','.join('?' for _ in self.active_roots)})", self.active_roots

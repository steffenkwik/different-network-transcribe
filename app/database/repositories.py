"""Small, parameterised repositories used by later application services."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.database.connection import transaction


def now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def last_row_id(cursor: sqlite3.Cursor) -> int:
    """Return an inserted row id with a concrete type for the repository API."""
    if cursor.lastrowid is None:
        raise RuntimeError("SQLite tidak mengembalikan ID baris baru.")
    return cursor.lastrowid


@dataclass(frozen=True)
class TranscriptListPage:
    rows: list[sqlite3.Row]
    total: int


class SettingsRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def set(self, key: str, value_json: str) -> None:
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                """
                INSERT INTO settings(key, value_json, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json,
                                              updated_at = excluded.updated_at
                """,
                (key, value_json, now()),
            )

    def get(self, key: str) -> str | None:
        row = self.connection.execute(
            "SELECT value_json FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return None if row is None else str(row["value_json"])


class TranscriptRepository:
    """Paged list queries deliberately never select transcript-body columns."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def list_page(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        state: str | None = None,
        basename_query: str | None = None,
    ) -> TranscriptListPage:
        conditions: list[str] = []
        params: list[object] = []
        if state is not None:
            conditions.append("current_state = ?")
            params.append(state)
        if basename_query:
            conditions.append("normalized_basename LIKE ?")
            params.append(f"%{basename_query.casefold()}%")
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        total = int(
            self.connection.execute(
                f"SELECT COUNT(*) FROM v_transcript_list{where}", params
            ).fetchone()[0]
        )
        rows = self.connection.execute(
            "SELECT id, stable_file_id, current_state, basename, duration_seconds, sender, chat, "
            "whatsapp_message_at, metadata_manually_corrected, match_status, confidence, model_name, "
            "quality_status, last_processed_at "
            f"FROM v_transcript_list{where} "
            "ORDER BY whatsapp_message_at IS NULL, whatsapp_message_at, stable_file_id LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return TranscriptListPage(rows=rows, total=total)

    def transcript_body(self, audio_file_id: int) -> sqlite3.Row | None:
        """Lazy detail lookup; list views never call this method."""
        return self.connection.execute(
            """
            SELECT a.id, a.stable_file_id, a.basename, t.raw_transcript, t.normalized_transcript,
                   t.segment_json, t.model_name, t.quality_status, t.completed_at
            FROM audio_files a
            LEFT JOIN transcription_attempts t ON t.id = a.preferred_transcript_id
            WHERE a.id = ?
            """,
            (audio_file_id,),
        ).fetchone()


class AudioRepository:
    """Persistence operations for discovery; all statements are parameterised."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def source_root(self, *, kind: str, original_path: str, normalized_path: str) -> int:
        row = self.connection.execute(
            "SELECT id FROM source_roots WHERE normalized_path = ?", (normalized_path,)
        ).fetchone()
        if row is not None:
            self.connection.execute(
                "UPDATE source_roots SET original_path = ?, enabled = 1 WHERE id = ?",
                (original_path, int(row["id"])),
            )
            return int(row["id"])
        cursor = self.connection.execute(
            """
            INSERT INTO source_roots(kind, original_path, normalized_path, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (kind, original_path, normalized_path, now()),
        )
        return last_row_id(cursor)

    def finish_root_scan(self, source_root_id: int) -> None:
        self.connection.execute(
            "UPDATE source_roots SET last_scanned_at = ? WHERE id = ?", (now(), source_root_id)
        )

    def audio_at_path(self, source_root_id: int, relative_path: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT a.*, v.id AS version_id, v.sha256 AS version_sha256
            FROM audio_files a
            LEFT JOIN audio_source_versions v ON v.id = a.current_source_version_id
            WHERE a.source_root_id = ? AND a.current_relative_path = ?
            """,
            (source_root_id, relative_path),
        ).fetchone()

    def audio_for_sha256(self, sha256: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT a.*, v.id AS matched_source_version_id
            FROM audio_source_versions v
            JOIN audio_files a ON a.id = v.audio_file_id
            WHERE v.sha256 = ?
            ORDER BY v.is_current DESC, a.id
            LIMIT 1
            """,
            (sha256,),
        ).fetchone()

    def create_audio(self, values: dict[str, Any]) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO audio_files(
                stable_file_id, source_root_id, current_relative_path, basename,
                normalized_basename, extension, size_bytes, windows_created_at,
                windows_modified_at, first_discovered_at, last_seen_at, duration_seconds,
                sha256, readable, zero_byte, current_state, created_at, updated_at
            ) VALUES (
                :stable_file_id, :source_root_id, :current_relative_path, :basename,
                :normalized_basename, :extension, :size_bytes, :windows_created_at,
                :windows_modified_at, :first_discovered_at, :last_seen_at, :duration_seconds,
                :sha256, :readable, :zero_byte, :current_state, :created_at, :updated_at
            )
            """,
            values,
        )
        return last_row_id(cursor)

    def add_source_version(
        self, audio_file_id: int, *, size_bytes: int, modified_at: str | None, sha256: str
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO audio_source_versions(audio_file_id, size_bytes, modified_at, sha256, discovered_at, is_current)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (audio_file_id, size_bytes, modified_at, sha256, now()),
        )
        return last_row_id(cursor)

    def mark_source_version_current(self, audio_file_id: int, source_version_id: int) -> None:
        timestamp = now()
        self.connection.execute(
            "UPDATE audio_source_versions SET is_current = 0, stale_at = ? WHERE audio_file_id = ? AND is_current = 1",
            (timestamp, audio_file_id),
        )
        self.connection.execute(
            "UPDATE audio_source_versions SET is_current = 1, stale_at = NULL WHERE id = ?",
            (source_version_id,),
        )
        self.connection.execute(
            "UPDATE audio_files SET current_source_version_id = ? WHERE id = ?",
            (source_version_id, audio_file_id),
        )

    def update_audio_observation(self, audio_file_id: int, values: dict[str, Any]) -> None:
        self.connection.execute(
            """
            UPDATE audio_files SET
                source_root_id = :source_root_id, current_relative_path = :current_relative_path,
                basename = :basename, normalized_basename = :normalized_basename,
                extension = :extension, size_bytes = :size_bytes,
                windows_created_at = :windows_created_at, windows_modified_at = :windows_modified_at,
                last_seen_at = :last_seen_at, duration_seconds = :duration_seconds, sha256 = :sha256,
                readable = :readable, zero_byte = :zero_byte, updated_at = :updated_at
            WHERE id = :id
            """,
            {**values, "id": audio_file_id},
        )

    def set_state(self, audio_file_id: int, state: str) -> None:
        self.connection.execute(
            "UPDATE audio_files SET current_state = ?, updated_at = ? WHERE id = ?",
            (state, now(), audio_file_id),
        )

    def record_path(self, audio_file_id: int, source_root_id: int, relative_path: str) -> None:
        timestamp = now()
        self.connection.execute(
            "UPDATE audio_path_history SET active = 0 WHERE audio_file_id = ?", (audio_file_id,)
        )
        self.connection.execute(
            """
            INSERT INTO audio_path_history(audio_file_id, source_root_id, relative_path, first_seen_at, last_seen_at, active)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(audio_file_id, source_root_id, relative_path)
            DO UPDATE SET last_seen_at = excluded.last_seen_at, active = 1
            """,
            (audio_file_id, source_root_id, relative_path, timestamp, timestamp),
        )

    def mark_missing_paths(self, source_root_id: int, seen_relative_paths: set[str]) -> int:
        rows = self.connection.execute(
            "SELECT id, current_relative_path, current_state FROM audio_files WHERE source_root_id = ?",
            (source_root_id,),
        ).fetchall()
        missing = [
            row for row in rows if str(row["current_relative_path"]) not in seen_relative_paths
        ]
        for row in missing:
            self.connection.execute(
                "UPDATE audio_path_history SET active = 0 WHERE audio_file_id = ?", (row["id"],)
            )
            if str(row["current_state"]) not in {"completed_preferred", "verified"}:
                self.set_state(int(row["id"]), "missing_source")
        return len(missing)

    def refresh_duplicate_groups(self) -> None:
        self.connection.execute("UPDATE audio_files SET duplicate_group = NULL")
        duplicate_names = self.connection.execute(
            """
            SELECT normalized_basename FROM audio_files
            GROUP BY normalized_basename HAVING COUNT(*) > 1
            """
        ).fetchall()
        for row in duplicate_names:
            basename = str(row["normalized_basename"])
            self.connection.execute(
                "UPDATE audio_files SET duplicate_group = ? WHERE normalized_basename = ?",
                (f"basename:{basename}", basename),
            )

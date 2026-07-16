"""Small, parameterised repositories used by later application services."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
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


@dataclass(frozen=True)
class TranscriptionCandidatePage:
    """A bounded, body-free file list for the pre-transcription dialog."""

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


class TranscriptionSelectionRepository:
    """Persist the user's explicit inclusion/exclusion of future audio work."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def candidates(self, source_root: Path | None, *, limit: int = 250, offset: int = 0) -> TranscriptionCandidatePage:
        if source_root is None:
            return TranscriptionCandidatePage(rows=[], total=0)
        root = str(source_root.resolve())
        where = """
            s.original_path = ?
            AND a.readable = 1 AND a.zero_byte = 0 AND a.current_source_version_id IS NOT NULL
            AND a.current_state NOT IN ('completed_preferred', 'verified', 'failed', 'no_speech', 'missing_source')
        """
        total = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM audio_files a JOIN source_roots s ON s.id = a.source_root_id WHERE " + where,
                (root,),
            ).fetchone()[0]
        )
        rows = self.connection.execute(
            """SELECT a.id, a.basename, a.current_relative_path, a.duration_seconds,
                      a.current_state, a.transcription_enabled
                 FROM audio_files a JOIN source_roots s ON s.id = a.source_root_id
                WHERE """ + where + " ORDER BY a.normalized_basename, a.id LIMIT ? OFFSET ?",
            (root, limit, offset),
        ).fetchall()
        return TranscriptionCandidatePage(rows=rows, total=total)

    def set_enabled(self, source_root: Path, audio_file_ids: list[int], *, enabled: bool) -> int:
        selected = sorted(set(audio_file_ids))
        if not selected:
            return 0
        root = str(source_root.resolve())
        placeholders = ",".join("?" for _ in selected)
        with transaction(self.connection, immediate=True):
            updated = self.connection.execute(
                f"""UPDATE audio_files
                    SET transcription_enabled = ?,
                        current_state = CASE
                            WHEN ? = 0 AND current_state NOT IN ('completed_preferred', 'verified', 'processing') THEN 'excluded'
                            WHEN ? = 1 AND current_state = 'excluded' THEN 'discovered'
                            ELSE current_state
                        END,
                        updated_at = ?
                    WHERE id IN ({placeholders})
                      AND source_root_id = (SELECT id FROM source_roots WHERE original_path = ?)
                      AND current_state != 'processing'""",
                [int(enabled), int(enabled), int(enabled), now(), *selected, root],
            )
        return updated.rowcount

    def replace_with(self, source_root: Path, selected_audio_file_ids: list[int]) -> int:
        """Make a deliberate small batch the only enabled incomplete work.

        This is used by the beginner-safe preflight: selecting a few files must
        never leave thousands of previously-default-enabled files ready by
        accident. Completed and currently processing rows are never altered.
        """
        root = str(source_root.resolve())
        selected = sorted(set(selected_audio_file_ids))
        candidate_where = """
            source_root_id = (SELECT id FROM source_roots WHERE original_path = ?)
            AND readable = 1 AND zero_byte = 0 AND current_source_version_id IS NOT NULL
            AND current_state NOT IN ('completed_preferred', 'verified', 'failed', 'no_speech', 'missing_source', 'processing')
        """
        with transaction(self.connection, immediate=True):
            self.connection.execute(
                "UPDATE audio_files SET transcription_enabled = 0, current_state = 'excluded', updated_at = ? WHERE "
                + candidate_where,
                (now(), root),
            )
            if not selected:
                return 0
            placeholders = ",".join("?" for _ in selected)
            cursor = self.connection.execute(
                f"""UPDATE audio_files SET transcription_enabled = 1,
                           current_state = CASE WHEN current_state = 'excluded' THEN 'discovered' ELSE current_state END,
                           updated_at = ?
                    WHERE id IN ({placeholders}) AND """ + candidate_where,
                [now(), *selected, root],
            )
        return cursor.rowcount

    def set_all_enabled(self, source_root: Path, *, enabled: bool) -> int:
        """Explicit bulk opt-in/out for users who intentionally want a full run."""
        root = str(source_root.resolve())
        with transaction(self.connection, immediate=True):
            cursor = self.connection.execute(
                """UPDATE audio_files
                       SET transcription_enabled = ?,
                           current_state = CASE
                               WHEN ? = 0 AND current_state NOT IN ('completed_preferred', 'verified', 'processing') THEN 'excluded'
                               WHEN ? = 1 AND current_state = 'excluded' THEN 'discovered'
                               ELSE current_state
                           END,
                           updated_at = ?
                     WHERE source_root_id = (SELECT id FROM source_roots WHERE original_path = ?)
                       AND readable = 1 AND zero_byte = 0 AND current_source_version_id IS NOT NULL
                       AND current_state NOT IN ('completed_preferred', 'verified', 'failed', 'no_speech', 'missing_source', 'processing')""",
                (int(enabled), int(enabled), int(enabled), now(), root),
            )
        return cursor.rowcount


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
        metadata_query: str | None = None,
        transcript_query: str | None = None,
        quality_status: str | None = None,
        model_name: str | None = None,
        match_status: str | None = None,
        whatsapp_date: str | None = None,
        sort: str = "whatsapp_asc",
        source_root: Path | None = None,
        review_only: bool = False,
    ) -> TranscriptListPage:
        conditions: list[str] = []
        params: list[object] = []
        if state is not None:
            conditions.append("v.current_state = ?")
            params.append(state)
        if basename_query:
            conditions.append("v.normalized_basename LIKE ?")
            params.append(f"%{basename_query.casefold()}%")
        if metadata_query:
            conditions.append(
                "(v.normalized_basename LIKE ? OR lower(COALESCE(v.sender, '')) LIKE ? "
                "OR lower(COALESCE(v.chat, '')) LIKE ?)"
            )
            query = f"%{metadata_query.casefold()}%"
            params.extend((query, query, query))
        if transcript_query:
            fts_query = _safe_fts_query(transcript_query)
            if fts_query:
                conditions.append("fts.text MATCH ?")
                params.append(fts_query)
        if quality_status:
            conditions.append("v.quality_status = ?")
            params.append(quality_status)
        if model_name:
            conditions.append("v.model_name = ?")
            params.append(model_name)
        if match_status:
            conditions.append("v.match_status = ?")
            params.append(match_status)
        if whatsapp_date:
            conditions.append("substr(v.whatsapp_message_at, 1, 10) = ?")
            params.append(whatsapp_date)
        if source_root is not None:
            conditions.append("s.original_path = ?")
            params.append(str(source_root.resolve()))
        if review_only:
            conditions.append(
                "(v.current_state IN ('failed', 'missing_source', 'stale_source_changed') "
                "OR COALESCE(v.match_status, '') IN "
                "('exact_ambiguous', 'filename_not_present', 'unmatched') "
                "OR COALESCE(v.quality_status, '') IN ('Perlu Diperiksa', 'Gagal'))"
            )
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        source = (
            " FROM v_transcript_list AS v "
            "JOIN audio_files AS a ON a.id = v.id "
            "JOIN source_roots AS s ON s.id = a.source_root_id"
        )
        if transcript_query and _safe_fts_query(transcript_query):
            source += " JOIN transcript_fts_map AS fm ON fm.audio_file_id = v.id"
            source += " JOIN transcript_fts AS fts ON fts.rowid = fm.rowid"
        total = int(
            self.connection.execute(
                f"SELECT COUNT(*){source}{where}", params
            ).fetchone()[0]
        )
        order_by = {
            "whatsapp_asc": "v.whatsapp_message_at IS NULL, v.whatsapp_message_at, v.stable_file_id",
            "whatsapp_desc": "v.whatsapp_message_at IS NULL, v.whatsapp_message_at DESC, v.stable_file_id",
            "filename": "v.normalized_basename, v.stable_file_id",
            "processed_desc": "v.last_processed_at IS NULL, v.last_processed_at DESC, v.stable_file_id",
        }.get(sort, "v.whatsapp_message_at IS NULL, v.whatsapp_message_at, v.stable_file_id")
        rows = self.connection.execute(
            "SELECT v.id, v.stable_file_id, v.current_state, v.basename, v.duration_seconds, v.sender, "
            "v.chat, v.whatsapp_message_at, v.metadata_manually_corrected, v.match_status, "
            "v.confidence, v.model_name, v.quality_status, v.last_processed_at "
            f"{source}{where} "
            f"ORDER BY {order_by} "
            "LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return TranscriptListPage(rows=rows, total=total)

    def transcript_body(self, audio_file_id: int) -> sqlite3.Row | None:
        """Lazy detail lookup; list views never call this method."""
        return self.connection.execute(
            """
            SELECT a.id, a.stable_file_id, a.basename, t.raw_transcript, t.normalized_transcript,
                   mt.text AS manual_transcript, t.segment_json, t.model_name, t.quality_status,
                   t.completed_at,
                   COALESCE(o.sender, r.sender_original) AS sender,
                   COALESCE(o.chat, r.chat_original) AS chat,
                   COALESCE(o.whatsapp_message_at, r.whatsapp_message_at) AS whatsapp_message_at
            FROM audio_files a
            LEFT JOIN transcription_attempts t ON t.id = a.preferred_transcript_id
            LEFT JOIN manual_transcripts mt ON mt.id = a.preferred_manual_transcript_id
            LEFT JOIN manual_metadata_overrides o ON o.audio_file_id = a.id AND o.active = 1
            LEFT JOIN metadata_matches m ON m.audio_file_id = a.id AND m.selected = 1
            LEFT JOIN chat_voice_references r ON r.id = m.chat_voice_reference_id
            WHERE a.id = ?
            """,
            (audio_file_id,),
        ).fetchone()


class TranscriptHistoryRepository:
    """Explicit, destructive transcript-history operations.

    This intentionally removes only derived transcript data.  Audio files, their
    paths, fingerprints, chat metadata, and source folders remain untouched.  A
    cleared record is disabled so it cannot accidentally enter a future queue;
    the user explicitly selects it again from the preflight dialog.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def clear_selected(self, audio_file_ids: list[int]) -> int:
        selected = sorted(set(audio_file_ids))
        if not selected:
            return 0
        placeholders = ",".join("?" for _ in selected)
        stamp = now()
        with transaction(self.connection, immediate=True):
            existing = self.connection.execute(
                f"SELECT id FROM audio_files WHERE id IN ({placeholders})", selected
            ).fetchall()
            ids = [int(row["id"]) for row in existing]
            if not ids:
                return 0
            ids_placeholders = ",".join("?" for _ in ids)
            self.connection.execute(
                f"""UPDATE audio_files
                       SET preferred_transcript_id = NULL,
                           preferred_manual_transcript_id = NULL,
                           transcription_enabled = 0,
                           current_state = CASE
                               WHEN readable = 1 AND zero_byte = 0
                                    AND current_source_version_id IS NOT NULL THEN 'discovered'
                               ELSE current_state
                           END,
                           updated_at = ?
                     WHERE id IN ({ids_placeholders})""",
                [stamp, *ids],
            )
            # Manual rows reference attempts, therefore they must go first.
            self.connection.execute(
                f"DELETE FROM manual_transcripts WHERE audio_file_id IN ({ids_placeholders})", ids
            )
            self.connection.execute(
                f"DELETE FROM transcription_attempts WHERE audio_file_id IN ({ids_placeholders})", ids
            )
            # This is a contentless FTS5 table, so SQLite does not support a
            # normal row DELETE. Rebuild from the authoritative preferred rows
            # after the small destructive operation instead.
            self.connection.execute("INSERT INTO transcript_fts(transcript_fts) VALUES ('delete-all')")
            self.connection.execute("DELETE FROM transcript_fts_map")
            self.connection.execute(
                """INSERT INTO transcript_fts(rowid, text)
                   SELECT a.id, COALESCE(mt.text, t.normalized_transcript, t.raw_transcript)
                     FROM audio_files AS a
                     JOIN transcription_attempts AS t ON t.id = a.preferred_transcript_id
                     LEFT JOIN manual_transcripts AS mt ON mt.id = a.preferred_manual_transcript_id
                    WHERE t.state = 'completed'
                      AND COALESCE(mt.text, t.normalized_transcript, t.raw_transcript) IS NOT NULL"""
            )
            self.connection.execute(
                """INSERT INTO transcript_fts_map(rowid, audio_file_id)
                   SELECT a.id, a.id
                     FROM audio_files AS a
                     JOIN transcription_attempts AS t ON t.id = a.preferred_transcript_id
                    WHERE t.state = 'completed'
                      AND COALESCE(t.normalized_transcript, t.raw_transcript) IS NOT NULL"""
            )
            self.connection.executemany(
                """INSERT INTO processing_events(audio_file_id, event_type, event_at, details_json)
                   VALUES (?, 'history_cleared', ?, '{\"scope\":\"transcript_history\"}')""",
                [(audio_id, stamp) for audio_id in ids],
            )
        return len(ids)


def _safe_fts_query(value: str) -> str:
    """Turn free-form UI input into literal FTS terms, not FTS syntax."""
    return " ".join(re.findall(r"\w+", value, flags=re.UNICODE))


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

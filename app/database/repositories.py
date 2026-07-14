"""Small, parameterised repositories used by later application services."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from app.database.connection import transaction


def now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


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
        row = self.connection.execute("SELECT value_json FROM settings WHERE key = ?", (key,)).fetchone()
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
            self.connection.execute(f"SELECT COUNT(*) FROM v_transcript_list{where}", params).fetchone()[0]
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

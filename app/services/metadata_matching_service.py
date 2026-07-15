"""Persist conservative audio/chat metadata matches for review and export."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from app.database.connection import transaction
from app.database.repositories import now
from app.matching.metadata_matcher import AudioCandidate, VoiceReferenceCandidate, match_audio


@dataclass(frozen=True)
class MatchingSummary:
    selected: int = 0
    ambiguous: int = 0
    unmatched: int = 0


class MetadataMatchingService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def run(self) -> MatchingSummary:
        audios = self.connection.execute(
            "SELECT id, normalized_basename, duration_seconds FROM audio_files ORDER BY id"
        ).fetchall()
        refs = self.connection.execute(
            """SELECT r.id,r.normalized_filename,r.sender_original,r.chat_original,r.whatsapp_message_at,
                      e.duplicate_of_id FROM chat_voice_references r JOIN chat_exports e ON e.id=r.chat_export_id"""
        ).fetchall()
        candidates = [
            VoiceReferenceCandidate(int(row["id"]), row["normalized_filename"], row["sender_original"],
                                    row["chat_original"], row["whatsapp_message_at"], row["duplicate_of_id"] is not None)
            for row in refs
        ]
        summary = MatchingSummary()
        for row in audios:
            result = match_audio(
                AudioCandidate(int(row["id"]), str(row["normalized_basename"]), row["duration_seconds"]), candidates
            )
            with transaction(self.connection, immediate=True):
                self.connection.execute("DELETE FROM metadata_matches WHERE audio_file_id = ?", (row["id"],))
                for reference_id in result.candidate_reference_ids:
                    self.connection.execute(
                        """INSERT INTO metadata_matches(audio_file_id,chat_voice_reference_id,match_status,confidence,
                           evidence_json,selected,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)""",
                        (row["id"], reference_id, result.match_status, result.confidence,
                         json.dumps({"matcher": "filename"}), int(result.selected and reference_id == result.reference_id), now(), now()),
                    )
            if result.selected:
                summary = MatchingSummary(summary.selected + 1, summary.ambiguous, summary.unmatched)
            elif result.match_status == "exact_ambiguous":
                summary = MatchingSummary(summary.selected, summary.ambiguous + 1, summary.unmatched)
            else:
                summary = MatchingSummary(summary.selected, summary.ambiguous, summary.unmatched + 1)
        return summary

"""Persist versioned WhatsApp-export references without retaining chat message bodies."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.database.connection import transaction
from app.database.repositories import AudioRepository, now
from app.parsing.whatsapp_parser import PARSER_VERSION, parse_export


@dataclass(frozen=True)
class ChatScanSummary:
    imported: int = 0
    unchanged: int = 0
    references: int = 0
    warnings: int = 0


class ChatImportService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.roots = AudioRepository(connection)

    def scan(self, root: Path) -> ChatScanSummary:
        root = root.resolve()
        if not root.is_dir():
            raise ValueError("Folder ekspor chat tidak ditemukan atau bukan folder.")
        with transaction(self.connection, immediate=True):
            root_id = self.roots.source_root(
                kind="chat", original_path=str(root), normalized_path=str(root).casefold()
            )
        summary = ChatScanSummary()
        for path in sorted(root.rglob("*.txt")):
            if not path.is_file():
                continue
            summary = self._import_one(root_id, root, path, summary)
        with transaction(self.connection, immediate=True):
            self.roots.finish_root_scan(root_id)
        return summary

    def _import_one(self, root_id: int, root: Path, path: Path, summary: ChatScanSummary) -> ChatScanSummary:
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        relative = path.relative_to(root).as_posix()
        existing = self.connection.execute(
            "SELECT id, sha256 FROM chat_exports WHERE source_root_id = ? AND relative_path = ?",
            (root_id, relative),
        ).fetchone()
        if existing is not None and existing["sha256"] == digest:
            return ChatScanSummary(
                imported=summary.imported, unchanged=summary.unchanged + 1,
                references=summary.references, warnings=summary.warnings
            )
        parsed = parse_export(raw.decode("utf-8", errors="replace"), chat_name=path.stem)
        with transaction(self.connection, immediate=True):
            canonical = self.connection.execute(
                "SELECT id FROM chat_exports WHERE sha256 = ? ORDER BY id LIMIT 1", (digest,)
            ).fetchone()
            if existing is None:
                cursor = self.connection.execute(
                    """INSERT INTO chat_exports(source_root_id,relative_path,sha256,inferred_chat_name,
                       parser_version,first_discovered_at,last_parsed_at,duplicate_of_id,parse_status,warning_count)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (root_id, relative, digest, path.stem, PARSER_VERSION, now(), now(),
                     None if canonical is None else canonical["id"], "ok", parsed.warning_count),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("SQLite tidak mengembalikan ID ekspor chat.")
                export_id = cursor.lastrowid
            else:
                export_id = int(existing["id"])
                self.connection.execute("DELETE FROM chat_voice_references WHERE chat_export_id = ?", (export_id,))
                self.connection.execute(
                    """UPDATE chat_exports SET sha256=?, inferred_chat_name=?, parser_version=?, last_parsed_at=?,
                       duplicate_of_id=?, parse_status='ok', warning_count=? WHERE id=?""",
                    (digest, path.stem, PARSER_VERSION, now(), None if canonical is None else canonical["id"],
                     parsed.warning_count, export_id),
                )
            self.connection.executemany(
                """INSERT INTO chat_voice_references(chat_export_id,line_number,sender_original,chat_original,
                   whatsapp_message_at,referenced_filename,normalized_filename,parser_pattern,parser_confidence,
                   warning,header_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                [(export_id, ref.line_number, ref.sender_original, ref.chat_original, ref.whatsapp_message_at,
                  ref.referenced_filename, ref.normalized_filename, ref.parser_pattern, ref.parser_confidence,
                  ref.warning, ref.header_hash) for ref in parsed.references],
            )
        return ChatScanSummary(
            imported=summary.imported + 1, unchanged=summary.unchanged,
            references=summary.references + len(parsed.references), warnings=summary.warnings + parsed.warning_count
        )

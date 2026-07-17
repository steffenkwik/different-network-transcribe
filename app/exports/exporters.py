"""Deterministic derived exports. SQLite remains the only source of truth."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from app.database.connection import transaction
from app.database.repositories import now
from app.version import APP_VERSION


@dataclass(frozen=True)
class ExportRecord:
    stable_id: str
    whatsapp_timestamp: str | None
    sender: str | None
    chat: str | None
    audio_filename: str
    audio_relative_path: str
    windows_created_at: str | None
    windows_modified_at: str | None
    discovered_at: str
    duration_seconds: float | None
    metadata_match_status: str | None
    metadata_confidence: float | None
    preferred_model: str
    quality_status: str | None
    preferred_transcript: str
    attempt_count: int
    processing_started_at: str | None
    processing_completed_at: str | None
    latest_error: str | None


@dataclass(frozen=True)
class ExportResult:
    """A named, user-visible export and the exact files it created."""

    records: int
    output_dir: Path
    files: tuple[Path, ...]


def atomic_write(path: Path, content: bytes) -> str:
    """Validate bytes before atomically replacing a derived artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    content.decode("utf-8-sig")
    temp.replace(path)
    return hashlib.sha256(content).hexdigest()


class ExportService:
    def __init__(
        self, connection: sqlite3.Connection, output_dir: Path, *, app_version: str = APP_VERSION
    ) -> None:
        self.connection = connection
        self.output_dir = output_dir
        self.app_version = app_version

    def records(self) -> list[ExportRecord]:
        rows = self.connection.execute(
            """
            SELECT a.stable_file_id, a.basename, a.current_relative_path, a.windows_created_at,
                   a.windows_modified_at, a.first_discovered_at, a.duration_seconds,
                   t.model_name, t.quality_status, t.normalized_transcript, t.raw_transcript,
                   mt.text AS manual_transcript,
                   t.started_at, t.completed_at, t.safe_error_message,
                   COALESCE(o.sender, r.sender_original) AS sender,
                   COALESCE(o.chat, r.chat_original) AS chat,
                   COALESCE(o.whatsapp_message_at, r.whatsapp_message_at) AS whatsapp_timestamp,
                   m.match_status, m.confidence,
                   (SELECT COUNT(*) FROM transcription_attempts x WHERE x.audio_file_id = a.id) AS attempt_count
            FROM audio_files a
            JOIN transcription_attempts t ON t.id = a.preferred_transcript_id
            LEFT JOIN manual_transcripts mt ON mt.id = a.preferred_manual_transcript_id
            LEFT JOIN manual_metadata_overrides o ON o.audio_file_id = a.id AND o.active = 1
            LEFT JOIN metadata_matches m ON m.audio_file_id = a.id AND m.selected = 1
            LEFT JOIN chat_voice_references r ON r.id = m.chat_voice_reference_id
            WHERE t.state = 'completed' AND COALESCE(t.normalized_transcript, t.raw_transcript) IS NOT NULL
            ORDER BY whatsapp_timestamp IS NULL, whatsapp_timestamp, a.stable_file_id
            """
        ).fetchall()
        return [
            ExportRecord(
                stable_id=str(row["stable_file_id"]),
                whatsapp_timestamp=row["whatsapp_timestamp"],
                sender=row["sender"],
                chat=row["chat"],
                audio_filename=str(row["basename"]),
                audio_relative_path=str(row["current_relative_path"]),
                windows_created_at=row["windows_created_at"],
                windows_modified_at=row["windows_modified_at"],
                discovered_at=str(row["first_discovered_at"]),
                duration_seconds=row["duration_seconds"],
                metadata_match_status=row["match_status"],
                metadata_confidence=row["confidence"],
                preferred_model=str(row["model_name"]),
                quality_status=row["quality_status"],
                preferred_transcript=str(
                    row["manual_transcript"] or row["normalized_transcript"] or row["raw_transcript"]
                ),
                attempt_count=int(row["attempt_count"]),
                processing_started_at=row["started_at"],
                processing_completed_at=row["completed_at"],
                latest_error=row["safe_error_message"],
            )
            for row in rows
        ]

    def export_all(
        self, *, include_individual: bool = False, include_generated_at: bool = False
    ) -> dict[str, int]:
        options_json = json.dumps(
            {
                "include_generated_at": include_generated_at,
                "include_individual": include_individual,
            },
            sort_keys=True,
        )
        with transaction(self.connection, immediate=True):
            cursor = self.connection.execute(
                """INSERT INTO export_runs(format, options_json, started_at, status)
                   VALUES ('all', ?, ?, 'running')""",
                (options_json, now()),
            )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite tidak mengembalikan ID ekspor.")
        export_run_id = int(cursor.lastrowid)
        try:
            records = self.records()
            self._markdown(records, include_individual, include_generated_at)
            self._text(records)
            self._csv(records)
            self._jsonl(records)
            with transaction(self.connection, immediate=True):
                self.connection.execute(
                    """UPDATE export_runs
                       SET completed_at = ?, record_count = ?, output_path = ?, output_sha256 = ?,
                           status = 'completed'
                       WHERE id = ?""",
                    (
                        now(),
                        len(records),
                        str(self.output_dir),
                        self._output_manifest_hash(),
                        export_run_id,
                    ),
                )
        except OSError as exc:
            with transaction(self.connection, immediate=True):
                self.connection.execute(
                    """UPDATE export_runs SET completed_at = ?, status = 'failed', error = ?
                       WHERE id = ?""",
                    (now(), type(exc).__name__, export_run_id),
                )
            raise
        return {"records": len(records)}

    def export_selected(
        self,
        *,
        name: str,
        formats: set[str],
        include_individual: bool = False,
        include_generated_at: bool = False,
    ) -> ExportResult:
        """Create only the formats chosen by the user in a named output folder.

        The legacy ``export_all`` output stays available for existing users and
        tests. New UI exports are intentionally self-contained: the folder,
        the file names, and the audit entry all carry the same user-facing
        name, so an Explorer button can always open the exact result.
        """
        allowed = {"markdown", "text", "csv", "jsonl"}
        chosen = set(formats)
        if not chosen:
            raise ValueError("Pilih minimal satu format hasil.")
        invalid = chosen - allowed
        if invalid:
            raise ValueError("Format hasil tidak dikenal.")
        safe_name = _safe_name(name)
        destination = self.output_dir / safe_name
        options_json = json.dumps(
            {
                "formats": sorted(chosen),
                "include_generated_at": include_generated_at,
                "include_individual": include_individual,
                "name": safe_name,
            },
            sort_keys=True,
        )
        with transaction(self.connection, immediate=True):
            cursor = self.connection.execute(
                """INSERT INTO export_runs(format, options_json, started_at, status)
                   VALUES ('selected', ?, ?, 'running')""",
                (options_json, now()),
            )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite tidak mengembalikan ID ekspor.")
        export_run_id = int(cursor.lastrowid)
        files: list[Path] = []
        try:
            records = self.records()
            if "markdown" in chosen:
                files.extend(
                    self._named_markdown(
                        records,
                        destination,
                        safe_name,
                        include_individual,
                        include_generated_at,
                    )
                )
            if "text" in chosen:
                files.append(self._named_text(records, destination, safe_name))
            if "csv" in chosen:
                files.append(self._named_csv(records, destination, safe_name))
            if "jsonl" in chosen:
                files.append(self._named_jsonl(records, destination, safe_name))
            with transaction(self.connection, immediate=True):
                self.connection.execute(
                    """UPDATE export_runs
                       SET completed_at = ?, record_count = ?, output_path = ?, output_sha256 = ?,
                           status = 'completed'
                       WHERE id = ?""",
                    (
                        now(),
                        len(records),
                        str(destination),
                        self._output_manifest_hash(destination),
                        export_run_id,
                    ),
                )
        except OSError as exc:
            with transaction(self.connection, immediate=True):
                self.connection.execute(
                    """UPDATE export_runs SET completed_at = ?, status = 'failed', error = ?
                       WHERE id = ?""",
                    (now(), type(exc).__name__, export_run_id),
                )
            raise
        return ExportResult(records=len(records), output_dir=destination, files=tuple(files))

    def _output_manifest_hash(self, directory: Path | None = None) -> str:
        """Hash derived artifacts for the export audit without changing their bytes."""
        root = directory or self.output_dir
        files = sorted(path for path in root.rglob("*") if path.is_file())
        manifest = [
            {
                "path": str(path.relative_to(root).as_posix()),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in files
        ]
        return hashlib.sha256(
            json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()

    def _named_markdown(
        self,
        records: list[ExportRecord],
        destination: Path,
        name: str,
        individual: bool,
        generated_at: bool,
    ) -> list[Path]:
        path = destination / "Markdown" / f"{name}.md"
        lines = ["---", "type: whatsapp_voice_note_transcripts", f"record_count: {len(records)}"]
        if generated_at:
            lines.append(f"generated_at: {datetime.now().astimezone().isoformat(timespec='seconds')}")
        lines.extend(["app: Different Network Transcribe", f"app_version: {self.app_version}", "---", ""])
        for record in records:
            lines.extend(self._markdown_entry(record))
        atomic_write(path, ("\n".join(lines).rstrip() + "\n").encode("utf-8"))
        files = [path]
        if individual:
            for record in records:
                individual_path = (
                    destination
                    / "Markdown"
                    / "Individual"
                    / f"{_safe_name(record.audio_filename)}__{record.stable_id[:8]}.md"
                )
                atomic_write(individual_path, ("\n".join(self._markdown_entry(record)) + "\n").encode("utf-8"))
                files.append(individual_path)
        return files

    def _named_text(self, records: list[ExportRecord], destination: Path, name: str) -> Path:
        path = destination / "Text" / f"{name}.txt"
        atomic_write(path, self._render_text(records).encode("utf-8"))
        return path

    def _named_csv(self, records: list[ExportRecord], destination: Path, name: str) -> Path:
        path = destination / "CSV" / f"{name}.csv"
        atomic_write(path, self._render_csv(records))
        return path

    def _named_jsonl(self, records: list[ExportRecord], destination: Path, name: str) -> Path:
        path = destination / "JSONL" / f"{name}.jsonl"
        atomic_write(path, self._render_jsonl(records))
        return path

    def _markdown(self, records: list[ExportRecord], individual: bool, generated_at: bool) -> None:
        daily: dict[str, list[ExportRecord]] = defaultdict(list)
        unknown: list[ExportRecord] = []
        for record in records:
            (
                daily[record.whatsapp_timestamp[:10]] if record.whatsapp_timestamp else unknown
            ).append(record)
        index: list[str] = ["# Indeks Transkrip", ""]
        for date, items in sorted(daily.items()):
            path = self.output_dir / "Markdown" / "Daily" / date[:4] / date[:7] / f"{date}.md"
            lines = [
                "---",
                "type: whatsapp_voice_note_transcripts",
                f"date: {date}",
                f"record_count: {len(items)}",
            ]
            if generated_at:
                lines.append(
                    f"generated_at: {datetime.now().astimezone().isoformat(timespec='seconds')}"
                )
            lines.extend(
                ["app: Different Network Transcribe", f"app_version: {self.app_version}", "---", ""]
            )
            for record in items:
                lines.extend(self._markdown_entry(record))
            atomic_write(path, ("\n".join(lines).rstrip() + "\n").encode("utf-8"))
            index.append(f"- [{date}](Daily/{date[:4]}/{date[:7]}/{date}.md) — {len(items)}")
        if unknown:
            lines = ["# Transkrip tanpa Timestamp WhatsApp", ""]
            for record in unknown:
                lines.extend(self._markdown_entry(record))
            atomic_write(
                self.output_dir / "Markdown" / "Unknown-Date.md",
                ("\n".join(lines).rstrip() + "\n").encode("utf-8"),
            )
        atomic_write(
            self.output_dir / "Markdown" / "INDEX.md", ("\n".join(index) + "\n").encode("utf-8")
        )
        if individual:
            for record in records:
                date = record.whatsapp_timestamp[:10] if record.whatsapp_timestamp else "unknown"
                name = f"{date}__{_safe_name(record.audio_filename)}__{record.stable_id[:8]}.md"
                atomic_write(
                    self.output_dir / "Markdown" / "Individual" / name,
                    ("\n".join(self._markdown_entry(record)) + "\n").encode("utf-8"),
                )

    def _markdown_entry(self, record: ExportRecord) -> list[str]:
        time = (
            record.whatsapp_timestamp[11:16]
            if record.whatsapp_timestamp
            else "Waktu tidak diketahui"
        )
        sender = record.sender or "Pengirim tidak diketahui"
        lines = [
            f'<a id="dnt-{record.stable_id[:8]}"></a>',
            f"## {time} — {sender}",
            "",
            f"- **Chat:** {record.chat or 'Tidak diketahui'}",
            f"- **Timestamp WhatsApp:** {record.whatsapp_timestamp or 'Timestamp WhatsApp tidak diketahui'}",
            f"- **File:** `{record.audio_filename}`",
            f"- **Model:** {record.preferred_model}",
            f"- **Kualitas:** {record.quality_status or 'Cukup'}",
            "",
            record.preferred_transcript,
            "",
        ]
        return lines

    def _text(self, records: list[ExportRecord]) -> None:
        atomic_write(
            self.output_dir / "Text" / "semua-transkrip.txt", self._render_text(records).encode("utf-8")
        )
        daily: dict[str, list[ExportRecord]] = defaultdict(list)
        for record in records:
            if record.whatsapp_timestamp:
                daily[record.whatsapp_timestamp[:10]].append(record)
        for date, items in daily.items():
            atomic_write(
                self.output_dir / "Text" / "Daily" / date[:4] / date[:7] / f"{date}.txt",
                self._render_text(items).encode("utf-8"),
            )

    def _csv(self, records: list[ExportRecord]) -> None:
        atomic_write(
            self.output_dir / "CSV" / "semua-transkrip.csv",
            self._render_csv(records),
        )

    def _jsonl(self, records: list[ExportRecord]) -> None:
        atomic_write(self.output_dir / "JSONL" / "semua-transkrip.jsonl", self._render_jsonl(records))

    @staticmethod
    def _render_text(records: list[ExportRecord]) -> str:
        lines: list[str] = []
        for record in records:
            lines.extend(
                [
                    "=" * 60,
                    f"Timestamp WhatsApp : {record.whatsapp_timestamp or 'Timestamp WhatsApp tidak diketahui'}",
                    f"Pengirim           : {record.sender or 'Pengirim tidak diketahui'}",
                    f"Chat               : {record.chat or 'Tidak diketahui'}",
                    f"Nama File          : {record.audio_filename}",
                    f"Model              : {record.preferred_model}",
                    f"Kualitas           : {record.quality_status or 'Cukup'}",
                    "=" * 60,
                    "",
                    record.preferred_transcript,
                    "",
                ]
            )
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _render_csv(records: list[ExportRecord]) -> bytes:
        import io

        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(ExportRecord.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(record) for record in records)
        return ("\ufeff" + stream.getvalue()).encode("utf-8")

    @staticmethod
    def _render_jsonl(records: list[ExportRecord]) -> bytes:
        content = "".join(
            json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n" for record in records
        )
        return content.encode("utf-8")


def _safe_name(name: str) -> str:
    safe = "".join("_" if char in '<>:"/\\|?*' else char for char in Path(name).stem).rstrip(". ")
    safe = safe or "unknown"
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}
    if safe.upper() in reserved:
        safe = f"_{safe}"
    return safe[:120]

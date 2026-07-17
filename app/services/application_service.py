"""Application-facing use cases used by the presentation layer.

The UI calls this facade; it never opens SQLite or invokes an engine itself.
Each operation owns a short-lived connection, so Qt threads can safely call it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app import config as config_mod
from app.backup.backup_service import BackupService
from app.database.connection import open_connection, transaction
from app.database.migrations import MigrationRunner
from app.database.repositories import (
    TranscriptHistoryRepository,
    TranscriptionCandidatePage,
    TranscriptionSelectionRepository,
    TranscriptListPage,
    TranscriptRepository,
    now,
)
from app.exports.exporters import ExportService
from app.paths import DataPaths
from app.runtime import bundled_path
from app.services.chat_import_service import ChatImportService, ChatScanSummary
from app.services.diagnostics_service import DiagnosticsService
from app.services.discovery_service import SUPPORTED_AUDIO_EXTENSIONS, DiscoveryService, ScanSummary
from app.services.metadata_matching_service import MatchingSummary, MetadataMatchingService
from app.services.worker_control_service import WorkerControlService
from app.transcription.model_registry import MODELS, ModelRegistry
from app.version import APP_VERSION


@dataclass(frozen=True)
class DashboardCounts:
    total: int
    completed: int
    pending: int
    review: int
    failed: int


@dataclass(frozen=True)
class TestBatchSummary:
    """The small, explicit test batch selected by a user before a real run."""

    source_count: int
    scan: ScanSummary


@dataclass(frozen=True)
class DirectFileBatchSummary:
    """An explicit local file batch added with the picker or drag-and-drop."""

    source_count: int
    selected_count: int
    scan: ScanSummary


class ApplicationService:
    """Orchestrates safe user operations without exposing infrastructure to Qt."""

    def __init__(self, paths: DataPaths) -> None:
        self.paths = paths

    def ensure_database(self) -> None:
        MigrationRunner(
            self.paths.database_file,
            bundled_path("migrations"),
            self.paths.backups_dir,
        ).migrate()

    def save_audio_root(self, folder: Path) -> None:
        if not folder.is_dir():
            raise ValueError("Folder audio tidak ditemukan atau bukan folder.")
        config = config_mod.load(self.paths.config_file, self.paths.config_lastgood_file)
        config.paths.audio_roots = [str(folder.resolve())]
        config_mod.save(config, self.paths.config_file, self.paths.config_lastgood_file)

    def configured_audio_root(self) -> Path | None:
        roots = self.configured_audio_roots()
        return roots[0] if roots else None

    def configured_audio_roots(self) -> list[Path]:
        """Return the current explicitly selected locations, never an inferred scan root."""
        config = config_mod.load(self.paths.config_file, self.paths.config_lastgood_file)
        roots: list[Path] = []
        seen: set[str] = set()
        for raw in config.paths.audio_roots:
            candidate = Path(raw).expanduser().resolve()
            key = str(candidate).casefold()
            if candidate.is_dir() and key not in seen:
                roots.append(candidate)
                seen.add(key)
        return roots

    def configured_chat_root(self) -> Path | None:
        config = config_mod.load(self.paths.config_file, self.paths.config_lastgood_file)
        if not config.paths.chat_roots:
            return None
        return Path(config.paths.chat_roots[0])

    def save_chat_root(self, folder: Path) -> None:
        if not folder.is_dir():
            raise ValueError("Folder ekspor chat tidak ditemukan atau bukan folder.")
        config = config_mod.load(self.paths.config_file, self.paths.config_lastgood_file)
        config.paths.chat_roots = [str(folder.resolve())]
        config_mod.save(config, self.paths.config_file, self.paths.config_lastgood_file)

    def scan_chats(self) -> ChatScanSummary:
        config = config_mod.load(self.paths.config_file, self.paths.config_lastgood_file)
        if not config.paths.chat_roots:
            raise ValueError("Pilih folder ekspor chat terlebih dahulu.")
        connection = open_connection(self.paths.database_file)
        try:
            return ChatImportService(connection).scan(Path(config.paths.chat_roots[0]))
        finally:
            connection.close()

    def scan_audio(self) -> ScanSummary:
        root = self.configured_audio_root()
        if root is None:
            raise ValueError("Pilih folder audio terlebih dahulu.")
        connection = open_connection(self.paths.database_file)
        try:
            return DiscoveryService(connection).scan_audio_root(root)
        finally:
            connection.close()

    def add_audio_files(
        self, files: list[Path], *, maximum_files: int = 20
    ) -> DirectFileBatchSummary:
        """Add a bounded, explicit list of local audio files without folder scanning.

        The source files stay exactly where they are.  Their parent folders are
        only stored as read-only locations so a worker can open each chosen file.
        Replacing the active selection makes the requested files the only queued
        candidates in those locations; it never touches completed transcripts.
        """
        selected = sorted({path.expanduser().resolve() for path in files}, key=lambda item: str(item).casefold())
        if not selected:
            raise ValueError("Pilih setidaknya satu file audio.")
        if len(selected) > maximum_files:
            raise ValueError(
                f"Pilih maksimal {maximum_files} file per batch langsung. "
                "Batas ini melindungi Anda dari transkripsi massal tidak sengaja."
            )
        invalid = [path.name for path in selected if not path.is_file() or path.suffix.casefold() not in SUPPORTED_AUDIO_EXTENSIONS]
        if invalid:
            raise ValueError("Ada file yang bukan audio didukung: " + ", ".join(invalid[:3]))

        roots = sorted({path.parent for path in selected}, key=lambda item: str(item).casefold())
        config = config_mod.load(self.paths.config_file, self.paths.config_lastgood_file)
        config.paths.audio_roots = [str(root) for root in roots]
        config_mod.save(config, self.paths.config_file, self.paths.config_lastgood_file)

        connection = open_connection(self.paths.database_file)
        try:
            scan = DiscoveryService(connection).scan_audio_files(selected)
            root_where, root_parameters = _source_root_filter(roots, "s.original_path")
            rows = connection.execute(
                """SELECT a.id, s.original_path, a.current_relative_path FROM audio_files AS a
                   JOIN source_roots AS s ON s.id = a.source_root_id
                   WHERE """ + root_where,
                root_parameters,
            ).fetchall()
            selected_keys = {
                (str(path.parent), path.name.casefold())
                for path in selected
            }
            selected_ids = [
                int(row["id"])
                for row in rows
                if (str(row["original_path"]), str(row["current_relative_path"])) in selected_keys
            ]
            enabled = TranscriptionSelectionRepository(connection).replace_with(roots, selected_ids)
        finally:
            connection.close()
        return DirectFileBatchSummary(
            source_count=len(selected), selected_count=enabled, scan=scan
        )

    def prepare_test_batch(self, folder: Path, *, maximum_files: int = 20) -> TestBatchSummary:
        """Make a user-selected small folder the active test root and scan it.

        The scan only proceeds when the folder contains from one to the requested
        maximum of supported audio files.  This keeps the documented beginner
        test path from accidentally selecting a whole WhatsApp archive.
        """
        if not folder.is_dir():
            raise ValueError("Folder audio uji tidak ditemukan atau bukan folder.")
        count = 0
        for candidate in folder.rglob("*"):
            if candidate.is_file() and candidate.suffix.casefold() in SUPPORTED_AUDIO_EXTENSIONS:
                count += 1
                if count > maximum_files:
                    raise ValueError(
                        f"Folder uji berisi lebih dari {maximum_files} audio. "
                        "Buat folder salinan kecil terlebih dahulu."
                    )
        if count == 0:
            raise ValueError("Folder uji tidak berisi audio yang didukung.")
        self.save_audio_root(folder)
        return TestBatchSummary(source_count=count, scan=self.scan_audio())

    def match_metadata(self) -> MatchingSummary:
        connection = open_connection(self.paths.database_file)
        try:
            return MetadataMatchingService(connection).run()
        finally:
            connection.close()

    def dashboard_counts(self) -> DashboardCounts:
        active_roots = self.configured_audio_roots()
        connection = open_connection(self.paths.database_file, read_only=True)
        try:
            where, parameters = _source_root_filter(active_roots, "s.original_path")
            rows = connection.execute(
                """SELECT a.current_state, COUNT(*) AS total
                   FROM audio_files a
                   JOIN source_roots s ON s.id = a.source_root_id
                   WHERE """ + where + " GROUP BY a.current_state",
                parameters,
            ).fetchall()
        finally:
            connection.close()
        counts = {str(row["current_state"]): int(row["total"]) for row in rows}
        return DashboardCounts(
            total=sum(counts.values()),
            completed=counts.get("completed_preferred", 0),
            pending=sum(
                counts.get(state, 0)
                for state in ("discovered", "queued", "processing", "stale_source_changed")
            ),
            review=sum(counts.get(state, 0) for state in ("failed", "missing_source")),
            failed=counts.get("failed", 0),
        )

    def transcription_candidates(self, *, limit: int = 250, offset: int = 0) -> TranscriptionCandidatePage:
        """Return a paged, transcript-body-free selection list for the start dialog."""
        connection = open_connection(self.paths.database_file, read_only=True)
        try:
            return TranscriptionSelectionRepository(connection).candidates(
                self.configured_audio_roots(), limit=limit, offset=offset
            )
        finally:
            connection.close()

    def set_transcription_selection(self, audio_file_ids: list[int], *, enabled: bool) -> int:
        """Persist an explicit selection without starting a worker or touching source files."""
        roots = self.configured_audio_roots()
        if not roots:
            raise ValueError("Pilih folder audio terlebih dahulu.")
        connection = open_connection(self.paths.database_file)
        try:
            return TranscriptionSelectionRepository(connection).set_enabled(
                roots, audio_file_ids, enabled=enabled
            )
        finally:
            connection.close()

    def replace_transcription_selection(self, selected_audio_file_ids: list[int]) -> int:
        """Choose an intentional small batch and exclude all other incomplete rows."""
        roots = self.configured_audio_roots()
        if not roots:
            raise ValueError("Pilih folder audio terlebih dahulu.")
        connection = open_connection(self.paths.database_file)
        try:
            return TranscriptionSelectionRepository(connection).replace_with(
                roots, selected_audio_file_ids
            )
        finally:
            connection.close()

    def set_all_transcription_enabled(self, *, enabled: bool) -> int:
        """Explicit bulk opt-in for the full pending collection; never implicit."""
        roots = self.configured_audio_roots()
        if not roots:
            raise ValueError("Pilih folder audio terlebih dahulu.")
        connection = open_connection(self.paths.database_file)
        try:
            return TranscriptionSelectionRepository(connection).set_all_enabled(roots, enabled=enabled)
        finally:
            connection.close()

    def transcript_page(
        self,
        *,
        limit: int,
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
    ) -> TranscriptListPage:
        connection = open_connection(self.paths.database_file, read_only=True)
        try:
            return TranscriptRepository(connection).list_page(
                limit=limit,
                offset=offset,
                state=state,
                basename_query=basename_query,
                metadata_query=metadata_query,
                transcript_query=transcript_query,
                quality_status=quality_status,
                model_name=model_name,
                match_status=match_status,
                whatsapp_date=whatsapp_date,
                sort=sort,
                source_roots=self.configured_audio_roots(),
            )
        finally:
            connection.close()

    def review_page(self, *, limit: int, offset: int = 0) -> TranscriptListPage:
        connection = open_connection(self.paths.database_file, read_only=True)
        try:
            return TranscriptRepository(connection).list_page(
                limit=limit,
                offset=offset,
                source_roots=self.configured_audio_roots(),
                review_only=True,
            )
        finally:
            connection.close()

    def transcript_detail(self, audio_file_id: int) -> sqlite3.Row:
        connection = open_connection(self.paths.database_file, read_only=True)
        try:
            detail = TranscriptRepository(connection).transcript_body(audio_file_id)
            if detail is None:
                raise ValueError("Transkrip tidak ditemukan.")
            return detail
        finally:
            connection.close()

    def source_path(self, audio_file_id: int) -> Path:
        """Return a source path for playback/open-location without mutating it."""
        connection = open_connection(self.paths.database_file, read_only=True)
        try:
            row = connection.execute(
                """SELECT s.original_path, a.current_relative_path
                   FROM audio_files AS a JOIN source_roots AS s ON s.id = a.source_root_id
                   WHERE a.id = ?""",
                (audio_file_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Rekaman audio tidak ditemukan.")
            root = Path(str(row["original_path"])).resolve()
            path = (root / str(row["current_relative_path"])).resolve()
            if root not in path.parents and path != root:
                raise ValueError("Lokasi sumber tidak aman.")
            if not path.is_file():
                raise ValueError("File sumber tidak ditemukan di lokasi yang tersimpan.")
            return path
        finally:
            connection.close()

    def save_manual_metadata(
        self,
        audio_file_id: int,
        *,
        sender: str | None,
        chat: str | None,
        whatsapp_message_at: str | None,
        note: str | None = None,
    ) -> None:
        """Write a new user override while retaining the parsed source metadata."""
        timestamp = _optional_text(whatsapp_message_at)
        if timestamp is not None:
            try:
                parsed = datetime.fromisoformat(timestamp)
            except ValueError as exc:
                raise ValueError("Timestamp WhatsApp harus ISO 8601, mis. 2026-07-16T20:31:00+07:00.") from exc
            if parsed.tzinfo is None:
                raise ValueError("Timestamp WhatsApp harus menyertakan zona waktu, mis. +07:00.")
        connection = open_connection(self.paths.database_file)
        try:
            with transaction(connection, immediate=True):
                exists = connection.execute("SELECT 1 FROM audio_files WHERE id = ?", (audio_file_id,)).fetchone()
                if exists is None:
                    raise ValueError("Rekaman audio tidak ditemukan.")
                revision = int(
                    connection.execute(
                        "SELECT COALESCE(MAX(revision), 0) + 1 FROM manual_metadata_overrides "
                        "WHERE audio_file_id = ?",
                        (audio_file_id,),
                    ).fetchone()[0]
                )
                connection.execute(
                    "UPDATE manual_metadata_overrides SET active = 0, updated_at = ? "
                    "WHERE audio_file_id = ? AND active = 1",
                    (now(), audio_file_id),
                )
                connection.execute(
                    """INSERT INTO manual_metadata_overrides(
                           audio_file_id, sender, chat, whatsapp_message_at, note, created_at,
                           updated_at, revision, active)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (
                        audio_file_id,
                        _optional_text(sender),
                        _optional_text(chat),
                        timestamp,
                        _optional_text(note),
                        now(),
                        now(),
                        revision,
                    ),
                )
        finally:
            connection.close()

    def save_manual_transcript(
        self, audio_file_id: int, *, text: str, note: str | None = None, verified: bool = False
    ) -> None:
        """Store an immutable human correction and explicitly make it preferred."""
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Transkrip manual tidak boleh kosong.")
        connection = open_connection(self.paths.database_file)
        try:
            with transaction(connection, immediate=True):
                audio = connection.execute(
                    "SELECT preferred_transcript_id FROM audio_files WHERE id = ?", (audio_file_id,)
                ).fetchone()
                if audio is None:
                    raise ValueError("Rekaman audio tidak ditemukan.")
                connection.execute(
                    "UPDATE manual_transcripts SET active = 0, updated_at = ? "
                    "WHERE audio_file_id = ? AND active = 1",
                    (now(), audio_file_id),
                )
                cursor = connection.execute(
                    """INSERT INTO manual_transcripts(
                           audio_file_id, based_on_attempt_id, text, verified, note, created_at,
                           updated_at, selected_as_preferred_at, active)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (
                        audio_file_id,
                        audio["preferred_transcript_id"],
                        cleaned,
                        int(verified),
                        _optional_text(note),
                        now(),
                        now(),
                        now(),
                    ),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("SQLite tidak mengembalikan ID koreksi manual.")
                connection.execute(
                    "UPDATE audio_files SET preferred_manual_transcript_id = ?, updated_at = ? WHERE id = ?",
                    (cursor.lastrowid, now(), audio_file_id),
                )
                connection.execute(
                    "INSERT OR REPLACE INTO transcript_fts(rowid, text) VALUES (?, ?)",
                    (audio_file_id, cleaned),
                )
                connection.execute(
                    """INSERT INTO transcript_fts_map(rowid, audio_file_id) VALUES (?, ?)
                       ON CONFLICT(audio_file_id) DO UPDATE SET rowid = excluded.rowid""",
                    (audio_file_id, audio_file_id),
                )
        finally:
            connection.close()

    def export_all(self) -> int:
        connection = open_connection(self.paths.database_file)
        try:
            return ExportService(connection, self.paths.output_dir, app_version=APP_VERSION).export_all()[
                "records"
            ]
        finally:
            connection.close()

    def create_backup(self) -> Path:
        return BackupService(
            self.paths.database_file,
            self.paths.backups_dir,
            app_version=APP_VERSION,
            models_dir=self.paths.models_dir,
        ).create_package(config_file=self.paths.config_file, include_output=self.paths.output_dir)

    def restore_backup(self, package: Path) -> None:
        if not package.is_file():
            raise ValueError("Paket backup tidak ditemukan.")
        BackupService(
            self.paths.database_file,
            self.paths.backups_dir,
            app_version=APP_VERSION,
            models_dir=self.paths.models_dir,
        ).restore_package(package, self.paths.database_file)
        self.ensure_database()

    def create_diagnostic_bundle(self) -> Path:
        return DiagnosticsService(
            self.paths.database_file,
            self.paths.logs_dir,
            self.paths.reports_dir,
            self.paths.models_dir,
        ).create_bundle()

    def model_status(self) -> dict[str, object]:
        config = config_mod.load(self.paths.config_file, self.paths.config_lastgood_file)
        registry = ModelRegistry(self.paths.models_dir).read()
        return {
            "default_model": config.transcription.default_model,
            "models": registry.get("models", {}),
        }

    def set_default_model(self, key: str) -> None:
        if key not in MODELS:
            raise ValueError("Model tidak dikenal.")
        ModelRegistry(self.paths.models_dir).verify(key, full_hash=False)
        config = config_mod.load(self.paths.config_file, self.paths.config_lastgood_file)
        config.transcription.default_model = key
        config_mod.save(config, self.paths.config_file, self.paths.config_lastgood_file)

    def import_model(self, key: str, archive: Path) -> Path:
        return ModelRegistry(self.paths.models_dir).import_zip(key, archive)

    def download_model(self, key: str) -> Path:
        return ModelRegistry(self.paths.models_dir).install_from_hub(key)

    def start_transcription(self) -> int:
        roots = self.configured_audio_roots()
        if not roots:
            raise ValueError("Tambahkan file audio atau pilih folder audio terlebih dahulu.")
        return self._worker_control().start()

    def pause_transcription(self) -> None:
        self._worker_control().pause()

    def resume_transcription(self) -> None:
        self._worker_control().resume()

    def transcription_state(self) -> str | None:
        session = self._worker_control().live_session()
        return None if session is None else session[1]

    def safe_stop_transcription(self) -> None:
        self._worker_control().safe_stop()

    def retry_failed_transcriptions(self) -> int | None:
        return self._worker_control().retry_failed()

    def reprocess_transcript(self, audio_file_id: int) -> int | None:
        """Ask the active worker to create a new attempt; history stays immutable."""
        return self._worker_control().reprocess_selected([audio_file_id])

    def clear_transcript_history(self, audio_file_ids: list[int]) -> int:
        """Forget selected derived transcripts while preserving source evidence.

        Clearing history during an active worker would race its per-file commit,
        so the user must pause/stop it first.  This never alters source audio or
        chat exports and leaves cleared files disabled until explicitly selected.
        """
        if self.transcription_state() is not None:
            raise RuntimeError("Jeda atau Berhenti Aman transkripsi sebelum menghapus riwayat.")
        connection = open_connection(self.paths.database_file)
        try:
            return TranscriptHistoryRepository(connection).clear_selected(audio_file_ids)
        finally:
            connection.close()

    def _worker_control(self) -> WorkerControlService:
        return WorkerControlService(self.paths.database_file, self.paths.root)


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def _source_root_filter(roots: list[Path], column: str) -> tuple[str, list[str]]:
    """Build a parameterised multi-root filter; an empty selection means all roots."""
    if not roots:
        return "1 = 1", []
    values = [str(root.resolve()) for root in roots]
    return f"{column} IN ({','.join('?' for _ in values)})", values

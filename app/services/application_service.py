"""Application-facing use cases used by the presentation layer.

The UI calls this facade; it never opens SQLite or invokes an engine itself.
Each operation owns a short-lived connection, so Qt threads can safely call it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app import config as config_mod
from app.backup.backup_service import BackupService
from app.database.connection import open_connection
from app.database.migrations import MigrationRunner
from app.database.repositories import TranscriptListPage, TranscriptRepository
from app.exports.exporters import ExportService
from app.paths import DataPaths
from app.services.chat_import_service import ChatImportService, ChatScanSummary
from app.services.discovery_service import DiscoveryService, ScanSummary
from app.services.worker_control_service import WorkerControlService
from app.version import APP_VERSION


@dataclass(frozen=True)
class DashboardCounts:
    total: int
    completed: int
    pending: int
    review: int
    failed: int


class ApplicationService:
    """Orchestrates safe user operations without exposing infrastructure to Qt."""

    def __init__(self, paths: DataPaths) -> None:
        self.paths = paths

    def ensure_database(self) -> None:
        MigrationRunner(
            self.paths.database_file,
            Path(__file__).resolve().parents[2] / "migrations",
            self.paths.backups_dir,
        ).migrate()

    def save_audio_root(self, folder: Path) -> None:
        if not folder.is_dir():
            raise ValueError("Folder audio tidak ditemukan atau bukan folder.")
        config = config_mod.load(self.paths.config_file, self.paths.config_lastgood_file)
        config.paths.audio_roots = [str(folder.resolve())]
        config_mod.save(config, self.paths.config_file, self.paths.config_lastgood_file)

    def configured_audio_root(self) -> Path | None:
        config = config_mod.load(self.paths.config_file, self.paths.config_lastgood_file)
        if not config.paths.audio_roots:
            return None
        return Path(config.paths.audio_roots[0])

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

    def dashboard_counts(self) -> DashboardCounts:
        connection = open_connection(self.paths.database_file, read_only=True)
        try:
            rows = connection.execute(
                "SELECT current_state, COUNT(*) AS total FROM audio_files GROUP BY current_state"
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

    def transcript_page(self, *, limit: int, offset: int = 0) -> TranscriptListPage:
        connection = open_connection(self.paths.database_file, read_only=True)
        try:
            return TranscriptRepository(connection).list_page(limit=limit, offset=offset)
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
            self.paths.database_file, self.paths.backups_dir, app_version=APP_VERSION
        ).create_package(config_file=self.paths.config_file)

    def start_transcription(self) -> int:
        return self._worker_control().start()

    def pause_transcription(self) -> None:
        self._worker_control().pause()

    def safe_stop_transcription(self) -> None:
        self._worker_control().safe_stop()

    def _worker_control(self) -> WorkerControlService:
        return WorkerControlService(self.paths.database_file, self.paths.root)

"""Data-folder layout.

Blueprint section 4.2: the database, models, outputs and private data must never
live under Program Files. Everything the user owns lives under a single data root
that they choose in the first-run wizard and can move later.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.version import APP_NAME

DEFAULT_DATA_DIR_NAME = f"{APP_NAME} Data"


def default_data_root() -> Path:
    """%USERPROFILE%\\Documents\\Different Network Transcribe Data (blueprint 4.2)."""
    return Path.home() / "Documents" / DEFAULT_DATA_DIR_NAME


@dataclass(frozen=True)
class DataPaths:
    """Every path the application writes to. Nothing outside this tree is ever written."""

    root: Path

    @property
    def database_dir(self) -> Path:
        return self.root / "Database"

    @property
    def database_file(self) -> Path:
        return self.database_dir / "different_network_transcribe.sqlite3"

    @property
    def models_dir(self) -> Path:
        return self.root / "Models"

    @property
    def model_registry_file(self) -> Path:
        return self.models_dir / "registry.json"

    @property
    def output_dir(self) -> Path:
        return self.root / "Output"

    @property
    def markdown_dir(self) -> Path:
        return self.output_dir / "Markdown"

    @property
    def text_dir(self) -> Path:
        return self.output_dir / "Text"

    @property
    def csv_dir(self) -> Path:
        return self.output_dir / "CSV"

    @property
    def jsonl_dir(self) -> Path:
        return self.output_dir / "JSONL"

    @property
    def individual_dir(self) -> Path:
        return self.output_dir / "Individual"

    @property
    def reports_dir(self) -> Path:
        return self.output_dir / "Reports"

    @property
    def backups_dir(self) -> Path:
        return self.root / "Backups"

    @property
    def logs_dir(self) -> Path:
        return self.root / "Logs"

    @property
    def temp_dir(self) -> Path:
        return self.root / "Temp"

    @property
    def config_dir(self) -> Path:
        return self.root / "Config"

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def config_lastgood_file(self) -> Path:
        """Last-known-good config (addendum 15.2)."""
        return self.config_dir / "config.lastgood.toml"

    @property
    def worker_status_file(self) -> Path:
        """Rate-limited worker progress snapshot (WORKER_IPC_CONTRACT section 7)."""
        return self.temp_dir / "worker_status.json"

    def all_dirs(self) -> list[Path]:
        return [
            self.database_dir,
            self.models_dir,
            self.output_dir,
            self.markdown_dir,
            self.text_dir,
            self.csv_dir,
            self.jsonl_dir,
            self.individual_dir,
            self.reports_dir,
            self.backups_dir,
            self.logs_dir,
            self.temp_dir,
            self.config_dir,
        ]

    def ensure(self) -> None:
        """Create the data tree. Idempotent."""
        for directory in self.all_dirs():
            directory.mkdir(parents=True, exist_ok=True)

    def is_writable(self) -> bool:
        """Addendum 19: never write persistent data into a read-only app directory.

        The portable build calls this before accepting a data root.
        """
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / ".dnt-write-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError:
            return False
        return True

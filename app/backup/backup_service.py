"""Consistent SQLite backup packages and staging-first restore."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.database.connection import integrity_check, open_connection
from app.database.migrations import backup_database


class BackupError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class BackupService:
    def __init__(self, database_file: Path, backups_dir: Path, *, app_version: str) -> None:
        self.database_file = database_file
        self.backups_dir = backups_dir
        self.app_version = app_version

    def create_package(
        self, *, config_file: Path | None = None, include_output: Path | None = None
    ) -> Path:
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
        package = self.backups_dir / f"DifferentNetworkTranscribe-Backup-{stamp}.dntbackup"
        with tempfile.TemporaryDirectory(prefix="dnt-backup-") as temp_name:
            temp = Path(temp_name)
            snapshot = backup_database(self.database_file, temp, label="database")
            manifest: dict[str, Any] = {
                "schema": 1,
                "app_version": self.app_version,
                "created_at": stamp,
                "database_sha256": _sha256(snapshot),
                "components": ["database"],
            }
            with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot, "Database/different_network_transcribe.sqlite3")
                if config_file and config_file.is_file():
                    archive.write(config_file, "Config/config.toml")
                    manifest["components"].append("config")
                if include_output and include_output.is_dir():
                    for file in include_output.rglob("*"):
                        if file.is_file():
                            archive.write(file, Path("Output") / file.relative_to(include_output))
                    manifest["components"].append("output")
                archive.writestr(
                    "manifest.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True)
                )
        return package

    def restore_package(self, package: Path, destination_database: Path) -> None:
        with tempfile.TemporaryDirectory(prefix="dnt-restore-") as temp_name:
            staging = Path(temp_name)
            try:
                with zipfile.ZipFile(package) as archive:
                    for member in archive.infolist():
                        if (
                            Path(member.filename).is_absolute()
                            or ".." in Path(member.filename).parts
                        ):
                            raise BackupError("Paket backup tidak aman.")
                        archive.extract(member, staging)
            except zipfile.BadZipFile as exc:
                raise BackupError("Paket backup tidak valid.") from exc
            manifest_file = staging / "manifest.json"
            database = staging / "Database" / "different_network_transcribe.sqlite3"
            if not manifest_file.is_file() or not database.is_file():
                raise BackupError("Paket backup tidak lengkap.")
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            if manifest.get("database_sha256") != _sha256(database):
                raise BackupError("Checksum database backup tidak cocok.")
            connection = open_connection(database)
            try:
                if integrity_check(connection) != "ok":
                    raise BackupError("Integritas database backup gagal.")
            finally:
                connection.close()
            destination_database.parent.mkdir(parents=True, exist_ok=True)
            # A restore must never overwrite the current live database without
            # first preserving a consistent SQLite snapshot of it.  The backup
            # API includes WAL state, unlike copying the database file directly.
            if destination_database.is_file():
                self.backups_dir.mkdir(parents=True, exist_ok=True)
                backup_database(destination_database, self.backups_dir, label="pre-restore")
            replacement = destination_database.with_suffix(".restore-staging.sqlite3")
            shutil.copy2(database, replacement)
            replacement.replace(destination_database)

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.backup.backup_service import BackupError, BackupService
from app.database.connection import open_connection
from app.database.migrations import MigrationRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.unit]


def test_package_restore_uses_consistent_database_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "source" / "Database" / "test.sqlite3"
    MigrationRunner(source, REPO_ROOT / "migrations", tmp_path / "source" / "Backups").migrate()
    connection = open_connection(source)
    connection.execute(
        "INSERT INTO settings(key,value_json,updated_at) VALUES ('theme','\"dark\"','t')"
    )
    connection.close()
    service = BackupService(source, tmp_path / "backups", app_version="0.1.0")
    package = service.create_package()
    target = tmp_path / "restored" / "Database" / "restored.sqlite3"
    service.restore_package(package, target)
    restored = open_connection(target, read_only=True)
    try:
        assert (
            restored.execute("SELECT value_json FROM settings WHERE key='theme'").fetchone()[0]
            == '"dark"'
        )
    finally:
        restored.close()


def test_backup_manifest_records_schema_components_and_audit(tmp_path: Path) -> None:
    source = tmp_path / "source" / "Database" / "test.sqlite3"
    MigrationRunner(source, REPO_ROOT / "migrations", tmp_path / "source" / "Backups").migrate()
    output = tmp_path / "source" / "Output"
    output.mkdir(parents=True)
    (output / "example.md").write_text("synthetic", encoding="utf-8")
    models = tmp_path / "source" / "Models"
    models.mkdir(parents=True)
    (models / "registry.json").write_text("{}", encoding="utf-8")
    service = BackupService(source, tmp_path / "backups", app_version="0.1.0", models_dir=models)
    package = service.create_package(include_output=output)
    with zipfile.ZipFile(package) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["database_schema_version"] == 5
    assert {"database", "output", "model_registry"} <= set(manifest["components"])
    connection = open_connection(source, read_only=True)
    try:
        assert connection.execute("SELECT status FROM backups").fetchone()[0] == "completed"
    finally:
        connection.close()


def test_restore_rejects_incomplete_package(tmp_path: Path) -> None:
    package = tmp_path / "empty.dntbackup"
    package.write_bytes(b"not a zip")
    with pytest.raises(BackupError, match="tidak valid"):
        BackupService(
            tmp_path / "missing.sqlite3", tmp_path / "backups", app_version="0"
        ).restore_package(package, tmp_path / "x.sqlite3")


def test_restore_backs_up_existing_destination_before_swap(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    MigrationRunner(source, REPO_ROOT / "migrations", tmp_path / "source-backups").migrate()
    source_connection = open_connection(source)
    source_connection.execute(
        "INSERT INTO settings(key,value_json,updated_at) VALUES ('source','true','t')"
    )
    source_connection.close()
    backups_dir = tmp_path / "backups"
    service = BackupService(source, backups_dir, app_version="0.1.0")
    package = service.create_package()

    destination = tmp_path / "destination.sqlite3"
    MigrationRunner(destination, REPO_ROOT / "migrations", tmp_path / "destination-backups").migrate()
    old_connection = open_connection(destination)
    old_connection.execute(
        "INSERT INTO settings(key,value_json,updated_at) VALUES ('old','true','t')"
    )
    old_connection.close()

    service.restore_package(package, destination)
    assert list(backups_dir.glob("pre-restore-*.sqlite3"))
    restored = open_connection(destination, read_only=True)
    try:
        assert restored.execute("SELECT value_json FROM settings WHERE key='source'").fetchone()[0] == "true"
        assert restored.execute("SELECT value_json FROM settings WHERE key='old'").fetchone() is None
    finally:
        restored.close()

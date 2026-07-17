"""Checksum-verified, backup-first SQLite migrations."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.database.connection import open_connection


class MigrationError(RuntimeError):
    """A database migration cannot be safely applied."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str
    accepted_checksums: frozenset[str]


def utc_now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def migration_catalog(migrations_dir: Path) -> list[Migration]:
    """Read numbered SQL migrations and reject ambiguous/invalid names."""
    migrations: list[Migration] = []
    seen_versions: set[int] = set()
    for path in sorted(migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        version_text, _, description = path.stem.partition("_")
        version = int(version_text)
        if version in seen_versions:
            raise MigrationError(f"Versi migrasi ganda: {version}")
        seen_versions.add(version)
        contents = path.read_bytes()
        migrations.append(
            Migration(
                version=version,
                name=description,
                path=path,
                checksum=hashlib.sha256(contents).hexdigest(),
                accepted_checksums=_checksum_variants(contents),
            )
        )
    if not migrations:
        raise MigrationError("Tidak ada berkas migrasi SQL.")
    return migrations


def _checksum_variants(contents: bytes) -> frozenset[str]:
    """Accept only byte-equivalent SQL with alternate Windows line endings.

    A few released Windows packages copied ``.sql`` resources with CRLF while
    the source/package used LF. SQLite executes both identically, but the
    previous raw-byte checksum gate treated an existing, official database as
    tampered. The variants below preserve the security boundary: any SQL token,
    comment, or whitespace change other than LF/CRLF still fails validation.
    """
    lf = contents.replace(b"\r\n", b"\n")
    variants = (contents, lf, lf.replace(b"\n", b"\r\n"))
    return frozenset(hashlib.sha256(item).hexdigest() for item in variants)


def backup_database(source: Path, backups_dir: Path, *, label: str = "pre-migration") -> Path:
    """Create a consistent snapshot using SQLite's online backup API."""
    backups_dir.mkdir(parents=True, exist_ok=True)
    destination = backups_dir / f"{label}-{utc_now().replace(':', '-')}.sqlite3"
    source_connection = open_connection(source)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()
    return destination


class MigrationRunner:
    """Applies each pending migration atomically and records its file checksum."""

    def __init__(self, database_file: Path, migrations_dir: Path, backups_dir: Path) -> None:
        self.database_file = database_file
        self.migrations_dir = migrations_dir
        self.backups_dir = backups_dir

    def _applied(self, connection: sqlite3.Connection) -> dict[int, str]:
        has_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'app_schema_migrations'"
        ).fetchone()
        if has_table is None:
            return {}
        return {
            int(row["version"]): str(row["checksum"])
            for row in connection.execute("SELECT version, checksum FROM app_schema_migrations")
        }

    def current_version(self) -> int:
        connection = open_connection(self.database_file)
        try:
            applied = self._applied(connection)
            return max(applied, default=0)
        finally:
            connection.close()

    def migrate(self) -> list[Migration]:
        """Validate history, back up the live DB, then atomically apply pending SQL."""
        catalog = migration_catalog(self.migrations_dir)
        connection = open_connection(self.database_file)
        try:
            applied = self._applied(connection)
            for migration in catalog:
                if (
                    migration.version in applied
                    and applied[migration.version] not in migration.accepted_checksums
                ):
                    raise MigrationError(
                        f"Checksum migrasi {migration.version:04d} tidak cocok; berkas pernah diubah."
                    )
            pending = [item for item in catalog if item.version not in applied]
            if not pending:
                return []
        finally:
            connection.close()

        # A new empty database has nothing valuable yet. Any existing schema is
        # backed up before even the first pending migration changes it.
        if self.database_file.exists() and self.database_file.stat().st_size > 0 and applied:
            backup_database(self.database_file, self.backups_dir)

        applied_now: list[Migration] = []
        connection = open_connection(self.database_file)
        try:
            for migration in pending:
                script = migration.path.read_text(encoding="utf-8")
                checksum_sql = migration.checksum.replace("'", "''")
                name_sql = migration.name.replace("'", "''")
                timestamp_sql = utc_now().replace("'", "''")
                # executescript commits a transaction opened externally, so the
                # transaction deliberately lives inside this script. SQLite DDL
                # is transactional; the migration row commits with the schema.
                atomic_script = (
                    "BEGIN IMMEDIATE;\n"
                    f"{script}\n"
                    "INSERT INTO app_schema_migrations(version, name, applied_at, checksum) "
                    f"VALUES ({migration.version}, '{name_sql}', '{timestamp_sql}', '{checksum_sql}');\n"
                    "COMMIT;"
                )
                try:
                    connection.executescript(atomic_script)
                except sqlite3.Error as exc:
                    with suppress(sqlite3.Error):
                        connection.execute("ROLLBACK")
                    raise MigrationError(
                        f"Migrasi {migration.version:04d}_{migration.name} gagal: {exc}"
                    ) from exc
                applied_now.append(migration)
            return applied_now
        finally:
            connection.close()

    def restore_latest_pre_migration_backup(self) -> Path:
        """Copy a consistent snapshot to staging; callers validate before swapping it."""
        backups = sorted(self.backups_dir.glob("pre-migration-*.sqlite3"))
        if not backups:
            raise MigrationError("Tidak ada backup pra-migrasi untuk dipulihkan.")
        staging = self.database_file.with_suffix(".restore-staging.sqlite3")
        shutil.copy2(backups[-1], staging)
        return staging

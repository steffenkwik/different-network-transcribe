from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.database.migrations import MigrationRunner
from app.services.diagnostics_service import DiagnosticsService

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.unit]


def test_diagnostic_bundle_excludes_private_values_and_source_files(tmp_path: Path) -> None:
    database = tmp_path / "Database" / "test.sqlite3"
    MigrationRunner(database, REPO_ROOT / "migrations", tmp_path / "Backups").migrate()
    logs = tmp_path / "Logs"
    logs.mkdir()
    secret = "synthetic private transcript must not ship"
    (logs / "worker.log").write_text(
        json.dumps({"msg": "failure", "data_root": "X:/private", "raw_transcript": secret}) + "\n",
        encoding="utf-8",
    )
    bundle = DiagnosticsService(database, logs, tmp_path / "Reports", tmp_path / "Models").create_bundle()
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        combined = "\n".join(archive.read(name).decode("utf-8", errors="ignore") for name in names)
    assert "report.json" in names
    assert secret not in combined
    assert "X:/private" not in combined
    assert not any(name.lower().endswith(".opus") for name in names)

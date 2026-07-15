"""Application use cases exercise services without importing the Qt layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.paths import DataPaths
from app.services.application_service import ApplicationService

pytestmark = [pytest.mark.unit]


def test_configured_scan_creates_records_and_exposes_paged_dashboard(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    source = tmp_path / "source"
    source.mkdir()
    (source / "one.opus").write_bytes(b"not-real-audio")
    service.save_audio_root(source)

    summary = service.scan_audio()
    assert summary.discovered == 1
    assert service.dashboard_counts().total == 1
    page = service.transcript_page(limit=10)
    assert page.total == 1
    assert page.rows[0]["basename"] == "one.opus"


def test_export_and_backup_are_available_without_presentation_layer(tmp_path: Path) -> None:
    paths = DataPaths(tmp_path / "data")
    paths.ensure()
    service = ApplicationService(paths)
    service.ensure_database()
    assert service.export_all() == 0
    assert service.create_backup().suffix == ".dntbackup"

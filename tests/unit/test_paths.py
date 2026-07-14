"""Data-folder layout (blueprint section 4.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.paths import DataPaths, default_data_root

pytestmark = pytest.mark.unit


def test_data_tree_matches_blueprint(tmp_path: Path) -> None:
    paths = DataPaths(root=tmp_path / "data")
    paths.ensure()

    expected = {
        "Database",
        "Models",
        "Output",
        "Output/Markdown",
        "Output/Text",
        "Output/CSV",
        "Output/JSONL",
        "Output/Individual",
        "Output/Reports",
        "Backups",
        "Logs",
        "Temp",
        "Config",
    }
    actual = {
        p.relative_to(paths.root).as_posix()
        for p in paths.root.rglob("*")
        if p.is_dir()
    }
    assert expected <= actual


def test_ensure_is_idempotent(tmp_path: Path) -> None:
    paths = DataPaths(root=tmp_path / "data")
    paths.ensure()
    paths.ensure()  # must not raise


def test_database_filename_is_exact() -> None:
    paths = DataPaths(root=Path("X:/data"))
    assert paths.database_file.name == "different_network_transcribe.sqlite3"
    assert paths.database_file.parent.name == "Database"


def test_default_root_is_not_program_files() -> None:
    """Blueprint 4.2: never store the database, models, outputs or private data
    under Program Files."""
    root = str(default_data_root()).lower()
    assert "program files" not in root
    assert root.endswith("different network transcribe data")


def test_writability_probe_cleans_up(tmp_path: Path) -> None:
    paths = DataPaths(root=tmp_path / "data")
    assert paths.is_writable() is True
    assert not (paths.root / ".dnt-write-probe").exists()

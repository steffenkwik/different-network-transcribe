"""Offline model-pack creation uses synthetic artifacts only."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app.transcription.model_packaging import build_model_pack
from app.transcription.model_registry import REQUIRED_FILES, ModelError

pytestmark = pytest.mark.unit


def test_model_pack_contains_required_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "Models" / "small"
    source.mkdir(parents=True)
    for name in REQUIRED_FILES:
        (source / name).write_text(name, encoding="utf-8")

    package = build_model_pack(tmp_path / "Models", "small", tmp_path / "release")

    with zipfile.ZipFile(package) as archive:
        assert set(archive.namelist()) >= REQUIRED_FILES


def test_model_pack_requires_complete_local_model(tmp_path: Path) -> None:
    with pytest.raises(ModelError, match="tidak ditemukan"):
        build_model_pack(tmp_path / "Models", "medium", tmp_path / "release")
